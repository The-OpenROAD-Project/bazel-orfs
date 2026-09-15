/* VeeR EH1 on the study's sim-control platform.
 *
 * The wrapper is simulation-only scaffolding: external memory, the
 * two-register sim-control device, and the AHB-Lite slaves that connect
 * them. Only the `swerv_wrapper` instance is ever hardened, and that
 * instance is already the study's boundary: swerv_wrapper contains both
 * `swerv` (the core) and `mem` (the 16 kB instruction cache and the
 * 64 kB DCCM), so core-plus-L1 is a module rather than a convention.
 *
 * Everything CoreMark touches in its hot loop is inside that boundary.
 * Instructions come from the icache, data and stack from the DCCM. What
 * remains on the external bus is instruction-cache miss traffic and the
 * two device words, and the first of those is counted rather than
 * assumed -- see `ifu_bus_xact` below.
 *
 * The rest of the SoC is tied off rather than built. VeeR's debug
 * system bus, its DMA slave, its JTAG port, its MPC halt/run interface
 * and its interrupt inputs all exist on the hardened block's port list
 * and are therefore paid for in area, leakage and clock power -- which
 * is correct, because that is what the repository delivers. They are
 * tied off outside the boundary, not inside it: tying them off within
 * the hardened module would let synthesis constant-propagate the debug
 * module away, and the measurement would quietly stop covering what the
 * core actually ships.
 *
 * The AHB-Lite slave follows the timing of upstream's own
 * testbench/ahb_sif.sv -- address phase captured on HREADY, data phase
 * the cycle after, zero wait states -- but is written here rather than
 * instantiated from there for two reasons: upstream's slave is backed
 * by an associative array that `$readmemh` cannot fill under Verilator,
 * and it decodes upstream's single 0xD0580000 mailbox rather than this
 * study's two-word contract, which every core in the study shares.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cm_soc #(
	/* 65536 words = 256 KiB of external memory at 0x8000_0000. The
	 * CoreMark image lives here and is fetched through the icache;
	 * nothing in the hot loop reads it twice. */
	parameter MEM_WORDS = 65536
) (
	input  wire        clk,
	input  wire        resetn,

	/* An exception. CoreMark on bare metal takes none, so this is a
	 * failure signal rather than a design one: it lets the harness stop
	 * at the cycle a run goes wrong instead of waiting out the cycle
	 * budget and reporting a timeout, which would say nothing about the
	 * cause. */
	output wire        trap,

	/* One character of stdout, valid for a single cycle. */
	output reg         out_valid,
	output reg  [7:0]  out_byte,

	/* The program has asked for the simulation to stop. */
	output reg         halt_valid,

	/* Retired-instruction address, for the harness to report where a run
	 * stopped when it stops without halting. A probe, not a design
	 * signal. */
	output wire [31:0] dbg_instr_addr
);
	localparam [31:0] SIM_CTRL_OUT  = 32'h1000_0000;
	localparam [31:0] SIM_CTRL_HALT = 32'h1000_0008;

	/* External memory base. Region 8, which the C runtime marks
	 * cacheable in MRAC so instruction fetches go through the icache --
	 * the L1 this study exists to measure. */
	localparam [31:0] EXTMEM_BASE = 32'h8000_0000;

	/* rst_vec is [31:1]: the core appends the implicit zero. */
	localparam [30:0] RESET_VEC = EXTMEM_BASE[31:1];

	/* ---------------- external memory ---------------- */

	reg [31:0] mem [0:MEM_WORDS-1];

	/* The image path is a run-time plusarg, not a parameter, so one
	 * compiled simulator runs both the two- and three-iteration
	 * programs. Rebuilding a gate-level simulator per program would
	 * dominate the cost of the whole measurement. */
	reg [8*256-1:0] meminit_path;
	initial begin
		if (!$value$plusargs("meminit=%s", meminit_path)) begin
			$display("cm_soc: +meminit=<path> is required");
			$finish;
		end
		$readmemh(meminit_path, mem);
	end

	function automatic [15:0] word_index(input [31:0] addr);
		word_index = addr[17:2];
	endfunction

	/* ---------------- IFU AHB-Lite master ---------------- */

	wire [31:0] ifu_haddr;
	wire [2:0]  ifu_hburst;
	wire        ifu_hmastlock;
	wire [3:0]  ifu_hprot;
	wire [2:0]  ifu_hsize;
	wire [1:0]  ifu_htrans;
	wire        ifu_hwrite;
	reg  [63:0] ifu_hrdata;

	/* Instruction-cache miss traffic, counted rather than assumed. A
	 * non-sequential or sequential transfer on this bus is a fetch the
	 * icache could not serve, so this is what turns "CoreMark fits in
	 * the instruction cache" from a claim into a number. */
	wire ifu_bus_xact = ifu_htrans[1];

	reg [31:0] ifu_addr_q;
	always @(posedge clk) begin
		if (!resetn) begin
			ifu_addr_q <= 32'b0;
			ifu_hrdata <= 64'b0;
		end else begin
			ifu_addr_q <= ifu_haddr;
			if (ifu_htrans[1]) begin
				ifu_hrdata <= {mem[word_index(ifu_haddr) + 16'd1],
				               mem[word_index(ifu_haddr)]};
			end
		end
	end

	/* ---------------- LSU AHB-Lite master ---------------- */

	wire [31:0] lsu_haddr;
	wire [2:0]  lsu_hburst;
	wire        lsu_hmastlock;
	wire [3:0]  lsu_hprot;
	wire [2:0]  lsu_hsize;
	wire [1:0]  lsu_htrans;
	wire        lsu_hwrite;
	wire [63:0] lsu_hwdata;
	reg  [63:0] lsu_hrdata;

	/* AHB byte lanes, as upstream's ahb_sif derives them. */
	function automatic [7:0] ahb_strobe(input [2:0] hsize, input [31:0] haddr);
		case (hsize)
			3'b000:  ahb_strobe = 8'h01 << haddr[2:0];
			3'b001:  ahb_strobe = 8'h03 << {haddr[2:1], 1'b0};
			3'b010:  ahb_strobe = 8'h0f << {haddr[2], 2'b0};
			default: ahb_strobe = 8'hff;
		endcase
	endfunction

	reg [31:0] lsu_addr_q;
	reg        lsu_write_q;
	reg [7:0]  lsu_strb_q;

	wire lsu_is_device_q = (lsu_addr_q[31:28] == 4'h1);

	always @(posedge clk) begin
		out_valid  <= 1'b0;

		if (!resetn) begin
			lsu_addr_q  <= 32'b0;
			lsu_write_q <= 1'b0;
			lsu_strb_q  <= 8'b0;
			lsu_hrdata  <= 64'b0;
			out_valid   <= 1'b0;
			out_byte    <= 8'b0;
			halt_valid  <= 1'b0;
		end else begin
			/* Address phase. HREADY is tied high, so every cycle with a
			 * live HTRANS starts a transfer. */
			lsu_addr_q  <= lsu_haddr;
			lsu_write_q <= lsu_htrans[1] & lsu_hwrite;
			lsu_strb_q  <= ahb_strobe(lsu_hsize, lsu_haddr);
			if (lsu_htrans[1] & ~lsu_hwrite) begin
				lsu_hrdata <= {mem[word_index(lsu_haddr) + 16'd1],
				               mem[word_index(lsu_haddr)]};
			end

			/* Data phase, one cycle later: HWDATA is valid now and the
			 * address it belongs to was captured above. */
			if (lsu_write_q) begin
				if (lsu_is_device_q) begin
					if (lsu_addr_q[3] == 1'b0) begin
						/* SIM_CTRL_OUT: the byte lane the store hit. */
						out_byte  <= lsu_hwdata[7:0];
						out_valid <= 1'b1;
					end else begin
						/* SIM_CTRL_HALT. */
						halt_valid <= 1'b1;
					end
				end else begin
					if (lsu_strb_q[0]) mem[word_index(lsu_addr_q)][ 7: 0] <= lsu_hwdata[ 7: 0];
					if (lsu_strb_q[1]) mem[word_index(lsu_addr_q)][15: 8] <= lsu_hwdata[15: 8];
					if (lsu_strb_q[2]) mem[word_index(lsu_addr_q)][23:16] <= lsu_hwdata[23:16];
					if (lsu_strb_q[3]) mem[word_index(lsu_addr_q)][31:24] <= lsu_hwdata[31:24];
					if (lsu_strb_q[4]) mem[word_index(lsu_addr_q) + 16'd1][ 7: 0] <= lsu_hwdata[39:32];
					if (lsu_strb_q[5]) mem[word_index(lsu_addr_q) + 16'd1][15: 8] <= lsu_hwdata[47:40];
					if (lsu_strb_q[6]) mem[word_index(lsu_addr_q) + 16'd1][23:16] <= lsu_hwdata[55:48];
					if (lsu_strb_q[7]) mem[word_index(lsu_addr_q) + 16'd1][31:24] <= lsu_hwdata[63:56];
				end
			end
		end
	end

	/* ---------------- the hardened block ---------------- */

	wire [63:0] trace_rv_i_insn_ip;
	wire [63:0] trace_rv_i_address_ip;
	wire [2:0]  trace_rv_i_valid_ip;
	wire [2:0]  trace_rv_i_exception_ip;
	wire [4:0]  trace_rv_i_ecause_ip;
	wire [2:0]  trace_rv_i_interrupt_ip;
	wire [31:0] trace_rv_i_tval_ip;

	assign dbg_instr_addr = trace_rv_i_address_ip[31:0];
	assign trap           = |trace_rv_i_exception_ip;

	/* Debug system bus master: outputs ignored, inputs parked. */
	wire [31:0] sb_haddr;
	wire [2:0]  sb_hburst;
	wire        sb_hmastlock;
	wire [3:0]  sb_hprot;
	wire [2:0]  sb_hsize;
	wire [1:0]  sb_htrans;
	wire        sb_hwrite;
	wire [63:0] sb_hwdata;

	/* DMA slave: never selected. */
	wire [63:0] dma_hrdata;
	wire        dma_hreadyout;
	wire        dma_hresp;

	wire [1:0] dec_tlu_perfcnt0;
	wire [1:0] dec_tlu_perfcnt1;
	wire [1:0] dec_tlu_perfcnt2;
	wire [1:0] dec_tlu_perfcnt3;

	wire jtag_tdo;
	wire mpc_debug_halt_ack;
	wire mpc_debug_run_ack;
	wire debug_brkpt_status;
	wire o_cpu_halt_ack;
	wire o_cpu_halt_status;
	wire o_debug_mode_status;
	wire o_cpu_run_ack;

	swerv_wrapper rvtop (
		.clk                     (clk),
		.rst_l                   (resetn),
		.dbg_rst_l               (resetn),
		.rst_vec                 (RESET_VEC),
		.nmi_int                 (1'b0),
		.nmi_vec                 (31'b0),
		.jtag_id                 (31'b0),

		.trace_rv_i_insn_ip      (trace_rv_i_insn_ip),
		.trace_rv_i_address_ip   (trace_rv_i_address_ip),
		.trace_rv_i_valid_ip     (trace_rv_i_valid_ip),
		.trace_rv_i_exception_ip (trace_rv_i_exception_ip),
		.trace_rv_i_ecause_ip    (trace_rv_i_ecause_ip),
		.trace_rv_i_interrupt_ip (trace_rv_i_interrupt_ip),
		.trace_rv_i_tval_ip      (trace_rv_i_tval_ip),

		/* IFU AHB master: instruction-cache refills. */
		.haddr                   (ifu_haddr),
		.hburst                  (ifu_hburst),
		.hmastlock               (ifu_hmastlock),
		.hprot                   (ifu_hprot),
		.hsize                   (ifu_hsize),
		.htrans                  (ifu_htrans),
		.hwrite                  (ifu_hwrite),
		.hrdata                  (ifu_hrdata),
		.hready                  (1'b1),
		.hresp                   (1'b0),

		/* LSU AHB master: the device, and anything outside the DCCM. */
		.lsu_haddr               (lsu_haddr),
		.lsu_hburst              (lsu_hburst),
		.lsu_hmastlock           (lsu_hmastlock),
		.lsu_hprot               (lsu_hprot),
		.lsu_hsize               (lsu_hsize),
		.lsu_htrans              (lsu_htrans),
		.lsu_hwrite              (lsu_hwrite),
		.lsu_hwdata              (lsu_hwdata),
		.lsu_hrdata              (lsu_hrdata),
		.lsu_hready              (1'b1),
		.lsu_hresp               (1'b0),

		/* Debug system bus: no debugger is attached. */
		.sb_haddr                (sb_haddr),
		.sb_hburst               (sb_hburst),
		.sb_hmastlock            (sb_hmastlock),
		.sb_hprot                (sb_hprot),
		.sb_hsize                (sb_hsize),
		.sb_htrans               (sb_htrans),
		.sb_hwrite               (sb_hwrite),
		.sb_hwdata               (sb_hwdata),
		.sb_hrdata               (64'b0),
		.sb_hready               (1'b1),
		.sb_hresp                (1'b0),

		/* DMA slave: nothing drives the core's memories from outside. */
		.dma_haddr               (32'b0),
		.dma_hburst              (3'b0),
		.dma_hmastlock           (1'b0),
		.dma_hprot               (4'b0),
		.dma_hsize               (3'b0),
		.dma_htrans              (2'b0),
		.dma_hwrite              (1'b0),
		.dma_hwdata              (64'b0),
		.dma_hsel                (1'b0),
		.dma_hreadyin            (1'b1),
		.dma_hrdata              (dma_hrdata),
		.dma_hreadyout           (dma_hreadyout),
		.dma_hresp               (dma_hresp),

		/* One bus clock per core clock: the external bus is not a
		 * divided domain here, so a miss costs what the memory costs and
		 * nothing more. */
		.lsu_bus_clk_en          (1'b1),
		.ifu_bus_clk_en          (1'b1),
		.dbg_bus_clk_en          (1'b1),
		.dma_bus_clk_en          (1'b1),

		.timer_int               (1'b0),
		.extintsrc_req           ('0),

		.dec_tlu_perfcnt0        (dec_tlu_perfcnt0),
		.dec_tlu_perfcnt1        (dec_tlu_perfcnt1),
		.dec_tlu_perfcnt2        (dec_tlu_perfcnt2),
		.dec_tlu_perfcnt3        (dec_tlu_perfcnt3),

		/* JTAG: parked. trst_n is held asserted-low so the TAP stays in
		 * reset rather than floating into an unknown state. */
		.jtag_tck                (1'b0),
		.jtag_tms                (1'b0),
		.jtag_tdi                (1'b0),
		.jtag_trst_n             (1'b0),
		.jtag_tdo                (jtag_tdo),

		/* MPC: run from reset, never halted. */
		.mpc_debug_halt_req      (1'b0),
		.mpc_debug_run_req       (1'b0),
		.mpc_reset_run_req       (1'b1),
		.mpc_debug_halt_ack      (mpc_debug_halt_ack),
		.mpc_debug_run_ack       (mpc_debug_run_ack),
		.debug_brkpt_status      (debug_brkpt_status),

		.i_cpu_halt_req          (1'b0),
		.o_cpu_halt_ack          (o_cpu_halt_ack),
		.o_cpu_halt_status       (o_cpu_halt_status),
		.o_debug_mode_status     (o_debug_mode_status),
		.i_cpu_run_req           (1'b0),
		.o_cpu_run_ack           (o_cpu_run_ack),

		.scan_mode               (1'b0),
		.mbist_mode              (1'b0)
	);
endmodule

`default_nettype wire
