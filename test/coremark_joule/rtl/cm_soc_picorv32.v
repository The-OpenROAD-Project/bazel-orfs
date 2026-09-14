/* picorv32 on the study's sim-control platform.
 *
 * The wrapper is simulation-only scaffolding: RAM, the two-register
 * sim-control device, and a bus adapter. Only the `picorv32` instance is
 * ever hardened, which is also what lets the gate-level simulator reuse
 * this file verbatim with the instance swapped for a netlist.
 *
 * The bus adapter is the only part that differs between the three cores
 * in the study. Everything above it -- the address map, the C runtime,
 * the CoreMark port -- is shared, which is the whole reason for writing
 * our own wrapper rather than adopting picorv32's testbench.v and then
 * porting the software again for SERV and again for ibex.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cm_soc #(
	/* 32768 words = 128 KiB, matching sw/port/link.ld. */
	parameter MEM_WORDS = 32768
) (
	input  wire        clk,
	input  wire        resetn,

	/* picorv32 raises trap on an illegal instruction or, with
	 * CATCH_MISALIGN, an unaligned access. Brought out so the harness
	 * can fail the run at the cycle it happens rather than waiting for
	 * the cycle budget to expire and reporting a timeout, which would
	 * say nothing about the cause. */
	output wire        trap,

	/* One character of stdout, valid for a single cycle. */
	output reg         out_valid,
	output reg  [7:0]  out_byte,

	/* The program has asked for the simulation to stop. */
	output reg         halt_valid
);
	localparam [31:0] SIM_CTRL_OUT  = 32'h1000_0000;
	localparam [31:0] SIM_CTRL_HALT = 32'h1000_0008;

	wire        mem_valid;
	wire        mem_instr;
	reg         mem_ready;
	wire [31:0] mem_addr;
	wire [31:0] mem_wdata;
	wire [ 3:0] mem_wstrb;
	reg  [31:0] mem_rdata;

	/* Bit 28 separates the device from RAM: RAM lives below 0x0002_0000
	 * and the device at 0x1000_0000, so one bit decides it. A full
	 * comparator would cost real cycles on the bit-serial core this
	 * address map also has to serve. */
	wire is_device = mem_addr[28];
	wire [$clog2(MEM_WORDS)-1:0] word_addr = mem_addr[$clog2(MEM_WORDS)+1:2];

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

	picorv32 #(
		/* rv32im. The multiplier and divider arrive through PCPI, which
		 * is also what makes them separate modules -- and therefore the
		 * only functional units picorv32 can be attributed to in the
		 * per-module power breakdown. The rest of the core is one
		 * module; see designs/asap7/picorv32/units.json. */
		.ENABLE_MUL(1),
		.ENABLE_DIV(1),
		/* Counters cost flops and the study never reads them: cycles
		 * are counted by the harness, so no core in the study needs a
		 * cycle CSR. Leaving them in would tax picorv32's area and
		 * power for something only picorv32 could offer. */
		.ENABLE_COUNTERS(0),
		.ENABLE_COUNTERS64(0),
		/* No interrupts anywhere in the study; crt0.S sets up none. */
		.ENABLE_IRQ(0),
		.PROGADDR_RESET(32'h0000_0000)
	) cpu (
		.clk       (clk),
		.resetn    (resetn),
		.trap      (trap),
		.mem_valid (mem_valid),
		.mem_instr (mem_instr),
		.mem_ready (mem_ready),
		.mem_addr  (mem_addr),
		.mem_wdata (mem_wdata),
		.mem_wstrb (mem_wstrb),
		.mem_rdata (mem_rdata),
		.mem_la_read  (),
		.mem_la_write (),
		.mem_la_addr  (),
		.mem_la_wdata (),
		.mem_la_wstrb (),
		.pcpi_valid (),
		.pcpi_insn  (),
		.pcpi_rs1   (),
		.pcpi_rs2   (),
		.pcpi_wr    (1'b0),
		.pcpi_rd    (32'b0),
		.pcpi_wait  (1'b0),
		.pcpi_ready (1'b0),
		.irq        (32'b0),
		.eoi        (),
		/* ENABLE_TRACE is 0, so these are tied off rather than used. */
		.trace_valid (),
		.trace_data  ()
	);

	/* One wait state on every access. Uniform latency keeps the cycle
	 * difference between the two runs a property of the core rather than
	 * of a memory model that might behave differently on the extra
	 * iteration's access pattern. */
	always @(posedge clk) begin
		mem_ready  <= 1'b0;
		out_valid  <= 1'b0;

		if (!resetn) begin
			mem_ready  <= 1'b0;
			out_valid  <= 1'b0;
			halt_valid <= 1'b0;
		end else if (mem_valid && !mem_ready) begin
			mem_ready <= 1'b1;

			if (is_device) begin
				mem_rdata <= 32'b0;
				if (mem_wstrb != 4'b0) begin
					if (mem_addr == SIM_CTRL_OUT) begin
						out_byte  <= mem_wdata[7:0];
						out_valid <= 1'b1;
					end
					if (mem_addr == SIM_CTRL_HALT && mem_wdata != 32'b0) begin
						halt_valid <= 1'b1;
					end
				end
			end else begin
				/* Read data is the pre-write value. CoreMark never reads
				 * and writes the same word in one transaction, and
				 * picorv32's bus cannot express it. */
				mem_rdata <= mem[word_addr];
				if (mem_wstrb[0]) mem[word_addr][ 7: 0] <= mem_wdata[ 7: 0];
				if (mem_wstrb[1]) mem[word_addr][15: 8] <= mem_wdata[15: 8];
				if (mem_wstrb[2]) mem[word_addr][23:16] <= mem_wdata[23:16];
				if (mem_wstrb[3]) mem[word_addr][31:24] <= mem_wdata[31:24];
			end
		end
	end
endmodule

`default_nettype wire
