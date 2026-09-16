/* picorv32 on the study's sim-control platform.
 *
 * Simulation-only scaffolding, and deliberately little of it. Everything
 * the benchmark touches once it is running -- the program, its data and
 * its stack -- lives in the two memories inside cmj_picorv32, which is what
 * gets hardened and what the energy number is reported over. What is
 * left out here is what the study's boundary (section 3.1) excludes:
 *
 *   - 64 KiB of external memory at 0x40000000, holding the boot stub
 *     and the load images of the sections crt0.S copies in. Read during
 *     boot and never again.
 *   - the two-register sim-control device at 0x10000000: one character
 *     of stdout, and a halt.
 *   - counters of everything that crossed the boundary, so "the hot
 *     loop never leaves the hardened block" is a measured number rather
 *     than a claim. Named as VeeR's are, so scripts/bus_probe.py reads
 *     all four cores the same way.
 *
 * The external port is the same on all three wrappers, and has two
 * sides because the tiles do: an instruction side and a data side. Each
 * presents its address combinationally and takes its answer on the next
 * cycle, matching what cmj_imem and cmj_dmem present, so the tile needs
 * one registered select per side rather than a skid buffer.
 *
 * Two read ports on one array is free here and would not be in silicon
 * -- which is exactly why it is on this side of the boundary. Nothing
 * in this file is hardened or measured; it exists so the boot copy can
 * fetch its own loop and read the image at the same time.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cm_soc #(
	/* 16384 words = 64 KiB at 0x40000000, matching sw/port/link.ld. */
	parameter ROM_WORDS = 16384
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
	output reg         halt_valid,

	/* Fetch address, for the harness to report where a run stopped when
	 * it stops without halting. A probe, not a design signal: it
	 * distinguishes a slow run from a trap loop, which otherwise look
	 * identical from outside. */
	output wire [31:0] dbg_instr_addr
);
	localparam [31:0] SIM_CTRL_OUT  = 32'h1000_0000;
	localparam [31:0] SIM_CTRL_HALT = 32'h1000_0008;
	localparam ROM_AW = $clog2(ROM_WORDS);

	wire        ext_i_req;
	wire [31:0] ext_i_addr;
	reg  [31:0] ext_i_rdata;

	wire        ext_d_req;
	wire        ext_d_we;
	wire [31:0] ext_d_addr;
	wire [31:0] ext_d_wdata;
	wire [ 3:0] ext_d_wstrb;
	reg  [31:0] ext_d_rdata;

	/* The boundary. Everything hardened, everything the SAIF covers and
	 * everything report_power totals is inside this instance. */
	cmj_picorv32 cpu (
		.clk         (clk),
		.resetn      (resetn),
		.trap        (trap),

		.ext_i_req   (ext_i_req),
		.ext_i_addr  (ext_i_addr),
		.ext_i_rdata (ext_i_rdata),

		.ext_d_req   (ext_d_req),
		.ext_d_we    (ext_d_we),
		.ext_d_addr  (ext_d_addr),
		.ext_d_wdata (ext_d_wdata),
		.ext_d_wstrb (ext_d_wstrb),
		.ext_d_rdata (ext_d_rdata),

		.dbg_instr_addr (dbg_instr_addr)
	);

	reg [31:0] rom [0:ROM_WORDS-1];

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
		$readmemh(meminit_path, rom);
	end

	wire is_device = ext_d_addr[28];
	wire [ROM_AW-1:0] iword = ext_i_addr[ROM_AW+1:2];
	wire [ROM_AW-1:0] dword = ext_d_addr[ROM_AW+1:2];

	/* Everything that crossed the boundary, counted on the cycle the
	 * transfer is presented -- which is also the only cycle it exists,
	 * since each side issues one access at a time. */
	reg [63:0] ifu_xacts;
	reg [63:0] lsu_xacts;

	always @(posedge clk) begin
		out_valid <= 1'b0;

		if (!resetn) begin
			halt_valid <= 1'b0;
			ifu_xacts  <= 64'd0;
			lsu_xacts  <= 64'd0;
		end else begin
			if (ext_i_req) begin
				ifu_xacts   <= ifu_xacts + 64'd1;
				ext_i_rdata <= rom[iword];
			end

			if (ext_d_req) begin
				lsu_xacts <= lsu_xacts + 64'd1;

				if (is_device) begin
					ext_d_rdata <= 32'b0;
					if (ext_d_we) begin
						if (ext_d_addr == SIM_CTRL_OUT) begin
							out_byte  <= ext_d_wdata[7:0];
							out_valid <= 1'b1;
						end
						if (ext_d_addr == SIM_CTRL_HALT && ext_d_wdata != 32'b0) begin
							halt_valid <= 1'b1;
						end
					end
				end else begin
					ext_d_rdata <= rom[dword];
					/* Read-only by construction: link.ld puts nothing
					 * writable out here, and crt0.S only ever reads. A
					 * write means the linker script and the address map
					 * have come apart, which is worth saying out loud
					 * rather than absorbing. */
					if (ext_d_we) begin
						$display("cm_soc: write to external memory at %h", ext_d_addr);
						$finish;
					end
				end
			end
		end
	end

	/* Written from a `final` block rather than on the halt write, so a
	 * run that stops on the cycle budget or on a trap still leaves the
	 * counts behind -- which is exactly the run whose bus traffic is
	 * worth looking at. The harness calls final() however the run ends. */
	reg [8*256-1:0] busprobe_path;
	reg             busprobe_on;
	integer         busprobe_fd;

	initial begin
		busprobe_on = $value$plusargs("busprobe=%s", busprobe_path);
	end

	final begin
		if (busprobe_on) begin
			busprobe_fd = $fopen(busprobe_path, "w");
			$fwrite(busprobe_fd, "ifu_xacts %0d\n", ifu_xacts);
			$fwrite(busprobe_fd, "lsu_xacts %0d\n", lsu_xacts);
			$fclose(busprobe_fd);
		end
	end
endmodule

`default_nettype wire
