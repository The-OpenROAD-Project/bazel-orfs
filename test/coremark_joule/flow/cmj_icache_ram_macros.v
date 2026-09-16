/* The flow's view of ibex's instruction-cache RAMs: ports, no body.
 *
 * Same role as cmj_progmem_macros.v. rtl/cmj_icache_ram.sv is the
 * behavioural view and is not in VERILOG_FILES; these boundaries are,
 * so yosys's hierarchy check passes and the .memories override turns
 * each into a FakeRAM macro. The port names are FakeRAM's exactly -- a
 * .memories override describes a boundary but does not rename the
 * generated macro's pins, so any other spelling links against the LEF
 * master and connects nothing.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cmj_ic_tag (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [ 7:0] addr_in,
	input  wire [21:0] wd_in,
	output wire [21:0] rd_out
);
endmodule

module cmj_ic_data (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [ 7:0] addr_in,
	input  wire [63:0] wd_in,
	output wire [63:0] rd_out
);
endmodule

`default_nettype wire
