/* The tightly-coupled memories the cacheless cores run out of, inside
 * the boundary. Behavioural view, for simulation only.
 *
 * Section 3.1's rule is that a core with no cache is measured together
 * with the small memory that holds the program its hot loop runs out
 * of. For picorv32, SERV and ibex that memory does not exist in their
 * repositories -- their testbenches use a simulation array -- so the
 * study supplies one and hardens it as part of the core. Section 5.1
 * reports what enforcing that cost.
 *
 * **Two memories, not one.** An instruction memory and a data memory at
 * disjoint addresses is what lets a fetch and a load proceed in the same
 * cycle without an arbiter. It is also what VeeR is -- an ICCM and a
 * DCCM at separate architectural addresses -- so the small cores are
 * structurally like the one they are compared against. And it removes a
 * combinational arbitration path ibex cannot take: its grants sit inside
 * its own documented combinational loops, and an arbiter that makes
 * instr_gnt depend on data_req joins them into one that never settles.
 *
 * **The interface is FakeRAM's, not firtool's, and that is not a
 * preference.** These are hardened by ORFS's AUTO_MEMORIES path, which
 * calls FakeRAM2.0 -- the generator that produced the platform's own
 * fakeram7_* views, and therefore the one VeeR's ICCM, DCCM and cache
 * arrays already use. Putting every point in the study on one memory
 * model is the whole reason for the choice: the memory is 58-85 % of
 * each point's power, and a cross-core energy comparison cannot afford
 * to have its largest term come from two different models.
 *
 * FakeRAM emits a fixed interface -- clk, ce_in, we_in, addr_in, wd_in,
 * rd_out -- and the `pins` in a .memories override do not rename it.
 * A module boundary that disagrees links anyway and wires nothing, so
 * these modules are written to match it exactly.
 *
 * **No write mask, hence cmj_dmem_lane.** That interface has no byte
 * enable: FakeRAM's ASAP7 RAM writes whole words. CoreMark stores bytes
 * and halfwords, so the data memory is four byte-wide macros with
 * independent we_in rather than one word-wide macro, and cmj_dmem.v
 * wires them up. The alternative -- read-modify-write in the tile for
 * sub-word stores -- would cost a cycle on some stores and move
 * CoreMark/MHz, and section 5.1's measurement depends on the memory
 * costing exactly zero cycles. The instruction memory needs no lanes:
 * the boot copy writes it a word at a time and nothing writes it after.
 * The lane split retires when FakeRAM gains a write mask; cmj_dmem.v
 * says what changes.
 *
 * Single-port costs nothing here. The data memory sees one access per
 * cycle on every core, and the instruction memory is written only by
 * the boot copy -- while that runs the core fetches from external
 * memory. The tiles assert both claims rather than trusting them.
 *
 * Sizes are from the images: the largest .text is 30,204 B and the
 * largest .rodata+.data+.bss is 3,588 B, so 32 KiB of instruction
 * memory and 8 KiB of data memory fit every march, with 4,604 B of
 * stack headroom against a measured high-water mark of 388 B. One pair
 * of sizes for every core and march, so the memory is a constant in the
 * comparison rather than a variable. link.ld carries the map and
 * asserts the fit.
 *
 * **Initialised by a boot copy, not by $readmemh.** A memory inside the
 * hardened block is blackboxed at synthesis, so the only way to fill it
 * from the harness is a hierarchical force into the behavioural array
 * -- which does not survive to the gate-level netlist, and the
 * gate-level run is the one that produces the SAIF. So the image is
 * loaded into external memory, crt0.S copies it in and jumps.
 *
 * The flow never sees this file: config.mk leaves it out of
 * VERILOG_FILES and names cmj_progmem_macros.v and a .memories file
 * instead, which is what makes AUTO_MEMORIES emit the macros and
 * blackbox the module names. Same split VeeR makes between mem_lib.sv
 * and its own macros.v.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

/* 8192 x 32 = 32 KiB, at 0x00000000. */
module cmj_imem (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [12:0] addr_in,
	input  wire [31:0] wd_in,
	output reg  [31:0] rd_out
);
	reg [31:0] mem [0:8191];

	always @(posedge clk) begin
		if (ce_in) begin
			if (we_in) begin
				mem[addr_in] <= wd_in;
			end else begin
				/* Synchronous read, which is what the generated Liberty
				 * characterises and what all three wrappers already
				 * presented: one wait state on every access. */
				rd_out <= mem[addr_in];
			end
		end
	end
endmodule

/* One byte lane of the data memory: 2048 x 8 = 2 KiB. Four of these
 * make the 8 KiB at 0x00010000; see cmj_dmem.v. */
module cmj_dmem_lane (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [10:0] addr_in,
	input  wire [ 7:0] wd_in,
	output reg  [ 7:0] rd_out
);
	reg [7:0] mem [0:2047];

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
