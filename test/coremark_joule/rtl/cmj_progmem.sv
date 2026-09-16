/* The tightly-coupled memories the cacheless cores run out of, inside
 * the boundary: two wiring wrappers around the SRAMs in
 * cmj_sram_models.sv.
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
 * **The memory model is tools/memory_macro_scaler's, and so is the port
 * convention.** Every SRAM in the study -- these two, VeeR's three and
 * ibex_icache's two -- is one behavioural module in cmj_sram_models.sv,
 * on firtool's RW0_* ports, and the scaler emits each one's LEF and
 * Liberty from that module's own widths. One model on every point is
 * the whole reason for the choice: the memory is over half of each
 * point's power, and a cross-core energy comparison cannot afford to
 * have its largest term come from two different models. Unlike
 * FakeRAM2.0, which this study used first, the scaler's energy and
 * leakage depend on the memory's shape (§5.1, §8.5).
 *
 * These wrappers keep the core-facing interface the tiles were written
 * against -- clk, ce_in, we_in, addr_in, wd_in, rd_out -- so swapping
 * the model changed the instance inside each wrapper and nothing above
 * it. They are pure wiring, not kept modules, and synthesis flattens
 * them away; the netlist instantiates the *_sram blackboxes directly.
 *
 * **Byte lanes.** The data memory is four byte-wide lanes with
 * independent enables rather than one masked word (cmj_dmem.v), a
 * layout FakeRAM's maskless interface forced and one this study keeps
 * so that the memory does not change shape under a model change. The
 * SRAM has a write mask now; a single 2048 x 32 macro with a byte mask
 * is a legitimate later change, and it changes every cacheless point.
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
 * The flow and the simulators both read this file. The flow pairs it
 * with flow/cmj_sram_blackbox.v (the *_sram module boundaries, no body)
 * and the scaler's LEF and Liberty; the simulators pair it with
 * cmj_sram_models.sv.
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
	output wire [31:0] rd_out
);
	cmj_imem_sram u_sram (
		.RW0_clk   (clk),
		.RW0_en    (ce_in),
		.RW0_wmode (we_in),
		.RW0_addr  (addr_in),
		.RW0_wmask ({32{1'b1}}),
		.RW0_wdata (wd_in),
		.RW0_rdata (rd_out)
	);
endmodule

/* One byte lane of the data memory: 2048 x 8 = 2 KiB. Four of these
 * make the 8 KiB at 0x00010000; see cmj_dmem.v. */
module cmj_dmem_lane (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [10:0] addr_in,
	input  wire [ 7:0] wd_in,
	output wire [ 7:0] rd_out
);
	cmj_dmem_lane_sram u_sram (
		.RW0_clk   (clk),
		.RW0_en    (ce_in),
		.RW0_wmode (we_in),
		.RW0_addr  (addr_in),
		.RW0_wmask ({8{1'b1}}),
		.RW0_wdata (wd_in),
		.RW0_rdata (rd_out)
	);
endmodule

`default_nettype wire
