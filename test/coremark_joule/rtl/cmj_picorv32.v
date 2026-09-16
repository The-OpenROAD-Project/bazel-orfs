/* The picorv32 tile this study measures: the core and its program SRAM.
 *
 * This module exists so the core that is simulated and the core that is
 * hardened cannot drift apart. picorv32's features are parameters with
 * defaults, and ENABLE_MUL/ENABLE_DIV default to 0 -- so hardening
 * `picorv32` directly would synthesise a core without the multiplier the
 * CoreMark/MHz number was measured on, and the energy per iteration
 * would be attributed to the wrong design.
 *
 * It is also the study's boundary. DESIGN_NAME in config.mk names this
 * module, so what is hardened, what the SAIF is captured over and what
 * report_power totals are all the same thing: the core plus the 32 KiB
 * instruction memory and 8 KiB data memory it runs out of. Section 3.1
 * says a cacheless core is measured with the memory its hot loop runs
 * out of, and everything inside this module is that; everything outside
 * it -- the external ROM the boot copy reads, the two-register
 * sim-control device -- is scaffolding the harness provides and the
 * measurement excludes.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cmj_picorv32 (
	input  wire        clk,
	input  wire        resetn,
	output wire        trap,

	/* Everything the tile could not serve itself, split the way the
	 * memories are: an instruction side and a data side. The address
	 * phase is combinational and the response arrives on the next
	 * cycle, which is exactly the timing cmj_imem and cmj_dmem present,
	 * so one registered select routes all four sources.
	 *
	 * picorv32 has a single bus, so at most one of the two is ever
	 * active; they are kept separate anyway so that the traffic counter
	 * on the other end reports fetches and data accesses apart, as
	 * VeeR's does. See cm_soc_picorv32.v. */
	output wire        ext_i_req,
	output wire [31:0] ext_i_addr,
	input  wire [31:0] ext_i_rdata,

	output wire        ext_d_req,
	output wire        ext_d_we,
	output wire [31:0] ext_d_addr,
	output wire [31:0] ext_d_wdata,
	output wire [ 3:0] ext_d_wstrb,
	input  wire [31:0] ext_d_rdata,

	/* Fetch address, for the harness to report where a run stopped when
	 * it stops without halting. A probe, not a design signal. */
	output wire [31:0] dbg_instr_addr
);
	wire        mem_valid;
	wire        mem_instr;
	reg         mem_ready;
	wire [31:0] mem_addr;
	wire [31:0] mem_wdata;
	wire [ 3:0] mem_wstrb;
	wire [31:0] mem_rdata;

	picorv32 #(
		/* The M extension, through PCPI. These are also the only
		 * functional units picorv32 can be attributed to in a
		 * per-module power breakdown: the rest of the core -- decode,
		 * execute, ALU, control -- is one module. */
		.ENABLE_MUL(1),
		.ENABLE_DIV(1),
		/* Counters cost flops and nothing in the study reads them:
		 * cycles are counted by the harness, so no core here needs a
		 * cycle CSR. Leaving them in would tax picorv32's area and
		 * power for a facility only picorv32 offers. */
		.ENABLE_COUNTERS(0),
		.ENABLE_COUNTERS64(0),
		/* No interrupts anywhere in the study. */
		.ENABLE_IRQ(0),
		/* External memory, not the TCM: the TCM is empty out of reset
		 * and the boot stub that fills it has to live somewhere the
		 * harness can preload. See sw/port/crt0.S. */
		.PROGADDR_RESET(32'h4000_0000)
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
		.trace_valid (),
		.trace_data  ()
	);

	assign dbg_instr_addr = mem_addr;

	/* Three bit tests decide the whole map, which is why link.ld puts
	 * the regions where it does: bit 30 is external memory
	 * (0x40000000), bit 28 the sim-control device (0x10000000), bit 16
	 * the data memory (0x00010000), and the instruction memory is what
	 * is left. A full comparator would cost real cycles on the
	 * bit-serial core this address map also has to serve. */
	wire is_ext  = mem_addr[30] | mem_addr[28];
	wire is_dmem = mem_addr[16];

	/* One wait state on every access, whichever side answers. Uniform
	 * latency keeps the cycle difference between the two runs a
	 * property of the core rather than of a memory model that might
	 * behave differently on the extra iteration's access pattern. */
	wire acc   = mem_valid && !mem_ready;
	wire is_wr = mem_wstrb != 4'b0;

	wire [31:0] im_rdata;
	wire [31:0] dm_rdata;

	/* FakeRAM's interface; see cmj_progmem.sv. picorv32 has a single
	 * bus and issues one access at a time, so a read and a write can
	 * never be requested together here. */
	cmj_imem u_imem (
		.clk     (clk),
		.ce_in   (acc && !is_ext && !is_dmem),
		.we_in   (is_wr),
		.addr_in (mem_addr[14:2]),
		.wd_in   (mem_wdata),
		.rd_out  (im_rdata)
	);

	cmj_dmem u_dmem (
		.clk      (clk),
		.ce_in    (acc && !is_ext && is_dmem),
		.we_in    (is_wr),
		.addr_in  (mem_addr[12:2]),
		.wd_in    (mem_wdata),
		.wstrb_in (mem_wstrb),
		.rd_out   (dm_rdata)
	);

	assign ext_i_req   = acc && is_ext && mem_instr;
	assign ext_i_addr  = mem_addr;

	assign ext_d_req   = acc && is_ext && !mem_instr;
	assign ext_d_we    = is_wr;
	assign ext_d_addr  = mem_addr;
	assign ext_d_wdata = mem_wdata;
	assign ext_d_wstrb = mem_wstrb;

	/* Which source answers the cycle mem_ready is high. All four
	 * register on the same edge, so the select is two flops and there
	 * is no latency to equalise. */
	reg sel_ext;
	reg sel_dmem;
	assign mem_rdata = sel_ext  ? (sel_dmem ? ext_d_rdata : ext_i_rdata)
	                            : (sel_dmem ? dm_rdata    : im_rdata);

	always @(posedge clk) begin
		mem_ready <= 1'b0;

		if (!resetn) begin
			mem_ready <= 1'b0;
		end else if (acc) begin
			mem_ready <= 1'b1;
			sel_ext   <= is_ext;
			sel_dmem  <= is_ext ? !mem_instr : is_dmem;
		end
	end
endmodule

`default_nettype wire
