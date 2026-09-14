/* The picorv32 configuration this study measures, frozen.
 *
 * This module exists so the core that is simulated and the core that is
 * hardened cannot drift apart. picorv32's features are parameters with
 * defaults, and ENABLE_MUL/ENABLE_DIV default to 0 -- so hardening
 * `picorv32` directly would synthesise a core without the multiplier the
 * CoreMark/MHz number was measured on, and the energy per iteration
 * would be attributed to the wrong design.
 *
 * DESIGN_NAME in config.mk names this module, and cm_soc_picorv32.v
 * instantiates it rather than picorv32 itself. Neither side can pick its
 * own parameters.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cmj_picorv32 (
	input  wire        clk,
	input  wire        resetn,
	output wire        trap,

	output wire        mem_valid,
	output wire        mem_instr,
	input  wire        mem_ready,
	output wire [31:0] mem_addr,
	output wire [31:0] mem_wdata,
	output wire [ 3:0] mem_wstrb,
	input  wire [31:0] mem_rdata
);
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
		.trace_valid (),
		.trace_data  ()
	);
endmodule

`default_nettype wire
