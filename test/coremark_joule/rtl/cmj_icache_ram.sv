/* ibex's instruction-cache RAMs: the behavioural view, simulation only.
 *
 * Same split as cmj_progmem.sv -- the flow gets a module boundary and a
 * .memories override, the gate-level simulation gets these. A macro is
 * blackboxed at synthesis, and a blackbox stores nothing, so a netlist
 * run without a behavioural model here would have an instruction cache
 * that never hits and CoreMark would fail its CRCs.
 *
 * Shapes and pin names are fixed by what they have to match: the two
 * banks ICache=1 asks for, on FakeRAM's interface. cmj_prim_ram_1p.sv
 * explains both.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

/* Tag bank: 256 x 22, one per way. */
module cmj_ic_tag (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [ 7:0] addr_in,
	input  wire [21:0] wd_in,
	output reg  [21:0] rd_out
);
	reg [21:0] mem [0:255];

	always @(posedge clk) begin
		if (ce_in) begin
			if (we_in) begin
				mem[addr_in] <= wd_in;
			end else begin
				rd_out <= mem[addr_in];
			end
		end
	end
endmodule

/* Data bank: 256 x 64, one per way. */
module cmj_ic_data (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [ 7:0] addr_in,
	input  wire [63:0] wd_in,
	output reg  [63:0] rd_out
);
	reg [63:0] mem [0:255];

	always @(posedge clk) begin
		if (ce_in) begin
			if (we_in) begin
				mem[addr_in] <= wd_in;
			end else begin
				rd_out <= mem[addr_in];
			end
		end
	end
endmodule

`default_nettype wire
