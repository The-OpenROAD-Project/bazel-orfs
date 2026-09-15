/* A design whose kept module is parameterized.
 *
 * The shell and Tcl halves of the name resolution are unit-tested
 * against a table, but the table is only as good as its idea of what
 * yosys emits. This is the end-to-end half: a module that reaches the
 * checkpoint under a mangled spelling, named in SYNTH_KEEP_MODULES by
 * its design name, on a design that synthesizes hierarchically.
 *
 * Before the fix, `grep '^module \\'` found no parameterized module at
 * all and synthesis stopped with
 *
 *   ERROR: SYNTH_KEEP_MODULES lists 'pk_unit' but it does not exist in
 *   the design.
 *
 * One parameter set, instantiated once. A module instantiated with
 * several parameter sets has several mangled names and the resolution
 * takes the first, which is a limitation the caller's error message is
 * meant to make visible rather than something this fixture pretends is
 * handled.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module pk_unit #(
	parameter integer W = 1
) (
	input  wire         clk,
	input  wire [W-1:0] d,
	output reg  [W-1:0] q
);
	always @(posedge clk) begin
		q <= d;
	end
endmodule

module pk_top (
	input  wire        clk,
	input  wire [3:0]  d,
	output wire [3:0]  q
);
	pk_unit #(
		.W(4)
	) u_unit (
		.clk(clk),
		.d  (d),
		.q  (q)
	);
endmodule

`default_nettype wire
