/* The smallest design that proves a simulator was built and ran.
 *
 * This exists for the link line, not for the logic. verilator's own
 * binary and every simulator it generates carry -latomic on Linux, and
 * under a zero-sysroot LLVM toolchain there is no libatomic to find --
 * so without the patches in MODULE.bazel neither this nor anything else
 * links. A counter is enough to make that a build failure someone sees.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module counter (
	input  wire        clk,
	input  wire        rst,
	output reg  [15:0] count
);
	always @(posedge clk) begin
		if (rst) begin
			count <= 16'd0;
		end else begin
			count <= count + 16'd1;
		end
	end
endmodule

`default_nettype wire
