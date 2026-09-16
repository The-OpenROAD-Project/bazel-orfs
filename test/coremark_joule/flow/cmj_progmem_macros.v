/* The flow's view of the two hardened memories: ports, no body.
 *
 * rtl/cmj_progmem.sv is the behavioural view and is deliberately not in
 * VERILOG_FILES -- handing both to one tool would leave it to choose
 * which to synthesise, and the answer would be flip-flops. But a module
 * that is nowhere defined fails yosys's hierarchy check during
 * canonicalization, before AUTO_MEMORIES has blackboxed anything:
 *
 *   ERROR: Module `\cmj_dmem_lane' referenced in module `\cmj_dmem' in
 *   cell `\u_lane' is not part of the design.
 *
 * So the flow gets the module boundary and nothing else, and the
 * .memories override supplies the geometry that turns each into a
 * FakeRAM macro. Same split VeeR makes between mem_lib.sv and its own
 * macros.v, and the same shape as asap7/tinyRocket's wrappers around
 * undefined _ext modules.
 *
 * The port names are FakeRAM's, exactly. A .memories override describes
 * the boundary but does not rename the generated macro's pins, so a
 * module declared with any other spelling links against the LEF master
 * and connects nothing -- silently, with plausible area.
 *
 * cmj_dmem is not here: it is wiring rather than storage, so both the
 * flow and the simulation read the one copy in rtl/cmj_dmem.v.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cmj_imem (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [12:0] addr_in,
	input  wire [31:0] wd_in,
	output wire [31:0] rd_out
);
endmodule

module cmj_dmem_lane (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [10:0] addr_in,
	input  wire [ 7:0] wd_in,
	output wire [ 7:0] rd_out
);
endmodule

`default_nettype wire
