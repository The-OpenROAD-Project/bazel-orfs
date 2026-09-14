/* SERV on the study's sim-control platform.
 *
 * Same wrapper contract as cm_soc_picorv32.v -- RAM, the two-register
 * sim-control device, and a bus adapter -- so the C runtime, the address
 * map and the CoreMark port are shared. Only serv_rf_top is hardened.
 *
 * SERV is not driven through servant, its reference SoC. servant's
 * "stdout" is a bit-banged UART on a one-bit GPIO decoded by
 * bench/uart_decoder.v: thousands of cycles per character, and dependent
 * on a baud rate. On a core that already needs ~10^8 cycles for one
 * CoreMark iteration, printing the report that way would be a
 * significant fraction of the measurement.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cm_soc #(
	parameter MEM_WORDS = 32768
) (
	input  wire        clk,
	input  wire        resetn,

	/* SERV has no trap output: an illegal instruction is not reported
	 * anywhere the wrapper can see. A broken run therefore shows up as
	 * a CRC mismatch or as the cycle budget expiring, never as a trap,
	 * which is a real difference in failure mode from picorv32 and is
	 * why the harness treats all three exits distinctly. */
	output wire        trap,

	output reg         out_valid,
	output reg  [7:0]  out_byte,
	output reg         halt_valid,

	/* Fetch address; see cm_soc_picorv32.v. */
	output wire [31:0] dbg_instr_addr
);
	localparam [31:0] SIM_CTRL_OUT  = 32'h1000_0000;
	localparam [31:0] SIM_CTRL_HALT = 32'h1000_0008;
	localparam AW = $clog2(MEM_WORDS);

	assign trap = 1'b0;

	wire [31:0] ibus_adr;
	wire        ibus_cyc;
	reg  [31:0] ibus_rdt;
	reg         ibus_ack;

	wire [31:0] dbus_adr;
	wire [31:0] dbus_dat;
	wire [ 3:0] dbus_sel;
	wire        dbus_we;
	wire        dbus_cyc;
	reg  [31:0] dbus_rdt;
	reg         dbus_ack;

	reg [31:0] mem [0:MEM_WORDS-1];

	reg [8*256-1:0] meminit_path;
	initial begin
		if (!$value$plusargs("meminit=%s", meminit_path)) begin
			$display("cm_soc: +meminit=<path> is required");
			$finish;
		end
		$readmemh(meminit_path, mem);
	end

	serv_rf_top #(
		.RESET_PC(32'h0000_0000),
		/* MINI resets only what is needed to restart from RESET_PC,
		 * which is what the harness provides; NONE would rely on a
		 * power-on state the netlist does not have. */
		.RESET_STRATEGY("MINI"),
		/* No compressed decoder: the study's ELFs are built without the
		 * C extension, so the decoder would be area and power that
		 * nothing in the measurement exercises. */
		.COMPRESSED(1'b0),
		/* No MDU. SERV is RV32I here, and CoreMark's multiplies go
		 * through libgcc -- which is the honest way to measure a core
		 * without the M extension. */
		.MDU(1'b0),
		.WITH_CSR(1),
		.W(1)
	) cpu (
		.clk         (clk),
		.i_rst       (~resetn),
		/* No timer interrupt: nothing in the study enables interrupts,
		 * and CoreMark's timer is stubbed to a constant. */
		.i_timer_irq (1'b0),

		.o_ibus_adr  (ibus_adr),
		.o_ibus_cyc  (ibus_cyc),
		.i_ibus_rdt  (ibus_rdt),
		.i_ibus_ack  (ibus_ack),

		.o_dbus_adr  (dbus_adr),
		.o_dbus_dat  (dbus_dat),
		.o_dbus_sel  (dbus_sel),
		.o_dbus_we   (dbus_we),
		.o_dbus_cyc  (dbus_cyc),
		.i_dbus_rdt  (dbus_rdt),
		.i_dbus_ack  (dbus_ack),

		.o_ext_rs1    (),
		.o_ext_rs2    (),
		.o_ext_funct3 (),
		.i_ext_rd     (32'b0),
		.i_ext_ready  (1'b0),
		.o_mdu_valid  ()
	);

	/* SERV has separate instruction and data buses onto one RAM, so the
	 * wrapper arbitrates. Data wins: the core is stalled waiting for it,
	 * while a fetch can always be retried a cycle later. On a bit-serial
	 * core the two are tens of cycles apart anyway, so the priority
	 * almost never binds and a fairer arbiter would buy nothing. */
	assign dbg_instr_addr = ibus_adr;

	wire serve_dbus = dbus_cyc && !dbus_ack;
	wire serve_ibus = ibus_cyc && !ibus_ack && !serve_dbus;

	wire is_device = dbus_adr[28];
	wire [AW-1:0] dword = dbus_adr[AW+1:2];
	wire [AW-1:0] iword = ibus_adr[AW+1:2];

	always @(posedge clk) begin
		ibus_ack  <= 1'b0;
		dbus_ack  <= 1'b0;
		out_valid <= 1'b0;

		if (!resetn) begin
			halt_valid <= 1'b0;
		end else if (serve_dbus) begin
			dbus_ack <= 1'b1;

			if (is_device) begin
				dbus_rdt <= 32'b0;
				if (dbus_we) begin
					if (dbus_adr == SIM_CTRL_OUT) begin
						out_byte  <= dbus_dat[7:0];
						out_valid <= 1'b1;
					end
					if (dbus_adr == SIM_CTRL_HALT && dbus_dat != 32'b0) begin
						halt_valid <= 1'b1;
					end
				end
			end else begin
				dbus_rdt <= mem[dword];
				if (dbus_we) begin
					if (dbus_sel[0]) mem[dword][ 7: 0] <= dbus_dat[ 7: 0];
					if (dbus_sel[1]) mem[dword][15: 8] <= dbus_dat[15: 8];
					if (dbus_sel[2]) mem[dword][23:16] <= dbus_dat[23:16];
					if (dbus_sel[3]) mem[dword][31:24] <= dbus_dat[31:24];
				end
			end
		end else if (serve_ibus) begin
			ibus_ack <= 1'b1;
			ibus_rdt <= mem[iword];
		end
	end
endmodule

`default_nettype wire
