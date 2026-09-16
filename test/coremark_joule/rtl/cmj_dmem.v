/* The data memory: four byte lanes with independent write enables.
 *
 * Read by both the simulation and the flow, unlike cmj_progmem.sv and
 * cmj_progmem_macros.v which are one or the other. There is nothing to
 * blackbox here -- this is wiring, not storage -- and keeping one copy
 * is what stops the lane order drifting between what is simulated and
 * what is hardened.
 *
 * Four lanes because FakeRAM's ASAP7 RAM has no byte enable; see
 * cmj_progmem.sv. A lane is written when the access is a write and its
 * strobe bit is set, and all four are read together.
 *
 * **This is a workaround with a known retirement.** FakeRAM is gaining
 * a write mask, and when that lands this module collapses to a single
 * 2048 x 32 macro with the strobe wired to its mask pin: delete the
 * generate block, instantiate cmj_dmem_lane's replacement once, and set
 * mask_lanes to 4 in flow/cmj_progmem.memories. Nothing above this
 * file changes -- the tiles already pass wstrb_in and know nothing
 * about lanes, which is why the wrapper exists rather than the tiles
 * instantiating four macros each.
 *
 * Expect the numbers to move slightly when it does: four 2048 x 8
 * macros and one 2048 x 32 are not the same area, and under FakeRAM's
 * per-macro energy model they are not the same power either (section
 * 5.1). CoreMark/MHz will not move -- neither shape costs a cycle.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cmj_dmem (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [10:0] addr_in,
	input  wire [31:0] wd_in,
	input  wire [ 3:0] wstrb_in,
	output wire [31:0] rd_out
);
	genvar i;
	generate
		for (i = 0; i < 4; i = i + 1) begin : lane
			cmj_dmem_lane u_lane (
				.clk     (clk),
				/* A read enables every lane; a write enables only the
				 * lanes its strobe selects, which is what makes a byte
				 * store a byte store. */
				.ce_in   (ce_in && (!we_in || wstrb_in[i])),
				.we_in   (we_in),
				.addr_in (addr_in),
				.wd_in   (wd_in[i*8 +: 8]),
				.rd_out  (rd_out[i*8 +: 8])
			);
		end
	endgenerate
endmodule

`default_nettype wire
