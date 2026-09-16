/* VeeR's memory modules, mapped onto the study's SRAM macros.
 *
 * Upstream's design/lib/mem_lib.sv defines ram_2048x39, ram_256x34 and
 * ram_64x21 as behavioural arrays. Those are the simulation view. This
 * file is the hardening view: the same three module names, the same
 * ports, each a wiring wrapper around the sram_* module of the matching
 * shape in rtl/cmj_sram_models.sv, whose LEF and Liberty
 * tools/memory_macro_scaler emits (flow/BUILD.bazel).
 *
 * Which is why mem_lib.sv is a separate filegroup in
 * //test/coremark_joule/rtl:veer_sim -- handing both to one tool would
 * leave it to choose between them. Synthesis reads this file with
 * flow/cmj_sram_blackbox.v and blackboxes the sram_* cells against their
 * Liberty views; the gate-level simulation reads cmj_sram_models.sv in
 * their place, which is the substitution §3.2 of the paper makes a
 * prerequisite rather than a refinement: a blackbox stores nothing, and
 * a register file that does not hold values fails CoreMark's CRCs
 * rather than quietly reporting low memory power.
 *
 * The shapes are not chosen here. They fall out of the configuration in
 * //test/coremark_joule/rtl/veer/config: a 16 kB instruction cache gives
 * ram_256x34 for its data and ram_64x21 for its tags, and a 64 kB DCCM
 * in eight banks gives ram_2048x39. They were first hardened as ASAP7's
 * fakeram7_* views of the same shapes; the wrappers are what let the
 * model change under them without touching the core.
 *
 * The wrappers are not kept modules, so synthesis flattens them away
 * and the netlist instantiates sram_* directly. VeeR writes whole
 * words, so the write mask is tied high and the enable to one, as the
 * fakeram7 wrappers before them did.
 *
 * Follows the shape of ORFS's own asap7/swerv_wrapper/macros.v, which
 * does the same job for the same core.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
module ram_2048x39 (CLK, ADR, D, Q, WE);
   input         CLK, WE;
   input  [10:0] ADR;
   input  [38:0] D;
   output [38:0] Q;
   sram_2048x39 mem (
      .RW0_clk   (CLK),
      .RW0_en    (1'b1),
      .RW0_wmode (WE),
      .RW0_addr  (ADR),
      .RW0_wmask ({39{1'b1}}),
      .RW0_wdata (D),
      .RW0_rdata (Q)
   );
endmodule

module ram_256x34 (CLK, ADR, D, Q, WE);
   input         CLK, WE;
   input  [7:0] ADR;
   input  [33:0] D;
   output [33:0] Q;
   sram_256x34 mem (
      .RW0_clk   (CLK),
      .RW0_en    (1'b1),
      .RW0_wmode (WE),
      .RW0_addr  (ADR),
      .RW0_wmask ({34{1'b1}}),
      .RW0_wdata (D),
      .RW0_rdata (Q)
   );
endmodule

module ram_64x21 (CLK, ADR, D, Q, WE);
   input         CLK, WE;
   input  [5:0] ADR;
   input  [20:0] D;
   output [20:0] Q;
   sram_64x21 mem (
      .RW0_clk   (CLK),
      .RW0_en    (1'b1),
      .RW0_wmode (WE),
      .RW0_addr  (ADR),
      .RW0_wmask ({21{1'b1}}),
      .RW0_wdata (D),
      .RW0_rdata (Q)
   );
endmodule
