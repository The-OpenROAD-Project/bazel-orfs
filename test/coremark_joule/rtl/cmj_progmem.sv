/* The two tightly-coupled memories the cacheless cores run out of,
 * inside the boundary.
 *
 * Section 3.1's rule is that a core with no cache is measured together
 * with the small memory that holds the program its hot loop runs out
 * of. For picorv32, SERV and ibex that memory does not exist in their
 * repositories -- their testbenches use a simulation array -- so the
 * study supplies one and hardens it as part of the core. Before this,
 * the three cacheless points were core-only, and section 4.6 put a
 * number on what that was worth: the cacheless extrapolation
 * overpredicted a boundary-compliant core by 15.2x.
 *
 * **Two memories, not one, and the split is load-bearing.** An
 * instruction memory and a data memory, addressed disjointly, is what
 * lets a fetch and a load proceed in the same cycle without an arbiter.
 * That matters for three reasons, in increasing order of importance:
 *
 *   - It is what these cores are actually deployed with. VeeR, the
 *     fourth core in this study, is built exactly this way: an ICCM and
 *     a DCCM at separate architectural addresses. A unified single-port
 *     memory would make the three small cores structurally unlike the
 *     one they are being compared against.
 *
 *   - An arbiter would be in the measurement. Whichever port loses
 *     stalls, and the stall rate depends on the core's load-to-fetch
 *     ratio -- so a shared port would charge SERV and ibex different
 *     amounts of CoreMark/MHz for a decision this study made, not for
 *     anything about the cores.
 *
 *   - It removes a combinational arbitration path that ibex cannot
 *     take. ibex's grant signals sit inside its own documented
 *     combinational loops (Verilator reports UNOPTFLAT on
 *     instr_executing_spec, id_in_ready and en_wb). An arbiter that
 *     makes instr_gnt depend on data_req joins those loops into one,
 *     and the grant stops settling to a single value: the symptom was a
 *     string loop that printed every other character, because the
 *     memory read port and the instruction grant disagreed about which
 *     master owned the cycle. With disjoint memories both grants are
 *     unconditional -- exactly what they were before this section --
 *     and the question does not arise.
 *
 * Sizes are from the images, not chosen. The largest .text in the study
 * (rv32i) is 30,204 B and the largest .rodata+.data+.bss is 3,588 B, so
 * 32 KiB of instruction memory and 8 KiB of data memory fit every
 * march, with 4,604 B of stack headroom against a measured high-water
 * mark of 388 B. One pair of sizes for all three cores and all three
 * marches, so the memory is a constant in the comparison instead of a
 * variable. link.ld carries the map and asserts the fit.
 *
 * **Written in firtool's port convention on purpose.** bazel-orfs's
 * memory_macro_scaler classifies a memory from its ports, and its
 * firtool path (R0_/W0_ groups) produces a real LEF and Liberty at
 * exactly the shape asked for. The name-suffix fallback that other port
 * spellings land in produces an empty LEF and a Liberty with no timing
 * arcs -- a stub, not a hardenable abstract. Since these modules are
 * ours to write, writing them in the convention the generator handles
 * is free, and it is what lets each core get macros at its own sizes
 * rather than a row of banks in whatever shapes the PDK happens to
 * ship.
 *
 * Both are 1R1W. The instruction memory's write port exists only for
 * the boot copy; the data memory's read and write ports are never used
 * in the same cycle by any core here, since all three issue one data
 * access at a time.
 *
 * **Initialised by a boot copy, not by $readmemh.** VeeR's ICCM taught
 * this the expensive way: a memory inside the hardened block is
 * blackboxed at synthesis, so the only way to fill it from the harness
 * is a hierarchical force into the behavioural array -- which does not
 * survive to the gate-level netlist, and the gate-level run is the one
 * that produces the SAIF. So the image is loaded into external memory,
 * crt0.S copies it in and jumps. The copy happens once, before the
 * first iteration, and the SAIF window is the last one.
 *
 * This file is the *behavioural* view, for simulation only. The flow
 * never sees it: config.mk leaves it out of VERILOG_FILES and the
 * generated Liberty blackboxes both module names, the same split VeeR
 * makes between mem_lib.sv and macros.v.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

/* 8192 x 32 = 32 KiB, at 0x00000000. */
module cmj_imem (
	input  wire [12:0] R0_addr,
	input  wire        R0_en,
	input  wire        R0_clk,
	output reg  [31:0] R0_data,

	input  wire [12:0] W0_addr,
	input  wire        W0_en,
	input  wire        W0_clk,
	input  wire [31:0] W0_data,
	input  wire [ 3:0] W0_mask
);
	reg [31:0] mem [0:8191];

	/* Synchronous read, which is what the generated Liberty
	 * characterises and what all three wrappers already presented: one
	 * wait state on every access. */
	always @(posedge R0_clk) begin
		if (R0_en) begin
			R0_data <= mem[R0_addr];
		end
	end

	always @(posedge W0_clk) begin
		if (W0_en) begin
			if (W0_mask[0]) mem[W0_addr][ 7: 0] <= W0_data[ 7: 0];
			if (W0_mask[1]) mem[W0_addr][15: 8] <= W0_data[15: 8];
			if (W0_mask[2]) mem[W0_addr][23:16] <= W0_data[23:16];
			if (W0_mask[3]) mem[W0_addr][31:24] <= W0_data[31:24];
		end
	end
endmodule

/* 2048 x 32 = 8 KiB, at 0x00010000. Holds .rodata, .data, .bss and the
 * stack -- everything the benchmark reads or writes as data. .rodata is
 * here rather than next to the code it belongs to precisely so that the
 * data side never reads the instruction memory. */
module cmj_dmem (
	input  wire [10:0] R0_addr,
	input  wire        R0_en,
	input  wire        R0_clk,
	output reg  [31:0] R0_data,

	input  wire [10:0] W0_addr,
	input  wire        W0_en,
	input  wire        W0_clk,
	input  wire [31:0] W0_data,
	input  wire [ 3:0] W0_mask
);
	reg [31:0] mem [0:2047];

	always @(posedge R0_clk) begin
		if (R0_en) begin
			R0_data <= mem[R0_addr];
		end
	end

	always @(posedge W0_clk) begin
		if (W0_en) begin
			if (W0_mask[0]) mem[W0_addr][ 7: 0] <= W0_data[ 7: 0];
			if (W0_mask[1]) mem[W0_addr][15: 8] <= W0_data[15: 8];
			if (W0_mask[2]) mem[W0_addr][23:16] <= W0_data[23:16];
			if (W0_mask[3]) mem[W0_addr][31:24] <= W0_data[31:24];
		end
	end
endmodule

`default_nettype wire
