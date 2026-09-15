/* A design that exercises both halves of AUTO_MEMORIES' classifier.
 *
 * The flow has one AUTO_MEMORIES design, asap7/tinyRocket, and it does
 * not set SYNTH_HIERARCHICAL -- so it takes the serial synthesis path,
 * and the parallel path had no coverage at all. That is where the bug
 * fixed by "AUTO_MEMORIES: make it work with parallel synthesis" lived,
 * and it is why this design exists.
 *
 * Two memories, deliberately of the two kinds the classifier has to
 * tell apart:
 *
 *   am_ram_2048x32  a module this file never defines. The .memories
 *                   override beside it carries the geometry, so
 *                   AUTO_MEMORIES converts it to a macro and blackboxes
 *                   the name. This is the convertible kind.
 *
 *   am_regs         an inline `reg [31:0] regs [0:31]` array inside a
 *                   module that also does something else. An inline
 *                   array is the design asking for flip-flops, and
 *                   converting it produces a macro nothing can
 *                   instantiate -- the failure "AUTO_MEMORIES: only
 *                   convert a memory that is its own module" fixes.
 *                   This is the kind that must be left alone, with a
 *                   reason recorded.
 *
 * 2048 x 32 is not an arbitrary shape either. FakeRAM folds an array by
 * column_mux_factor, and at 2048 deep the difference between folding
 * and not is the difference between a 33 x 84 um macro and a 4 x 664 um
 * sliver no floorplan can place.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

/* The kind that must NOT be converted: an array inside a module that is
 * not itself a memory. */
module am_regs (
	input  wire        clk,
	input  wire        we,
	input  wire [ 4:0] waddr,
	input  wire [31:0] wdata,
	input  wire [ 4:0] raddr,
	output reg  [31:0] rdata,
	output reg         parity
);
	reg [31:0] regs [0:31];

	always @(posedge clk) begin
		if (we) begin
			regs[waddr] <= wdata;
		end
		rdata <= regs[raddr];
		/* Something other than the array, so this module is not simply
		 * a memory wearing a wrapper. */
		parity <= ^wdata;
	end
endmodule

module am_top (
	input  wire        clk,
	input  wire        en,
	input  wire        we,
	input  wire [10:0] addr,
	input  wire [31:0] wdata,
	output wire [31:0] rdata,
	output wire [31:0] regs_rdata,
	output wire        parity
);
	/* Undefined here on purpose: AUTO_MEMORIES converts it from the
	 * .memories override and blackboxes the name. FakeRAM's pin
	 * spelling, which a .memories override describes but does not
	 * rename -- a module declared any other way links against the LEF
	 * master and connects nothing. */
	am_ram_2048x32 u_ram (
		.clk     (clk),
		.ce_in   (en),
		.we_in   (we),
		.addr_in (addr),
		.wd_in   (wdata),
		.rd_out  (rdata)
	);

	am_regs u_regs (
		.clk    (clk),
		.we     (we),
		.waddr  (addr[4:0]),
		.wdata  (wdata),
		.raddr  (addr[10:6]),
		.rdata  (regs_rdata),
		.parity (parity)
	);
endmodule

`default_nettype wire
