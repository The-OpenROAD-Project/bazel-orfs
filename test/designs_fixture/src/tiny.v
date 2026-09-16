/* A design whose sources are named by a "//" label.
 *
 * That is the point of it. config_mk_parser resolves such a label
 * against the root of the repository the designs tree lives in, and
 * that root used to be computed by stripping two path components --
 * correct for ORFS's flow/designs and wrong for a tree at any other
 * depth. Every design in such a tree then looked like it had missing
 * sources and was skipped, silently.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module tiny (
	input  wire       clk,
	input  wire [7:0] d,
	output reg  [7:0] q
);
	always @(posedge clk) begin
		q <= d;
	end
endmodule

`default_nettype wire
