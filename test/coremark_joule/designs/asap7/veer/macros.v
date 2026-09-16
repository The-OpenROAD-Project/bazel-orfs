/* VeeR's memory modules, mapped onto the ASAP7 SRAM macros.
 *
 * Upstream's design/lib/mem_lib.sv defines ram_2048x39, ram_256x34 and
 * ram_64x21 as behavioural arrays. Those are the simulation view. This
 * file is the hardening view: the same three module names, the same
 * ports, each wrapping the fakeram7 macro of the matching shape that
 * ASAP7 already carries.
 *
 * Which is why mem_lib.sv is a separate filegroup in
 * //test/coremark_joule/rtl:veer_sim -- handing both to one tool would
 * leave it to choose between them. Synthesis reads this file and blackboxes
 * the fakeram7 cells against their Liberty views; the gate-level
 * simulation reads the platform's own fakeram7_*.v behavioural models in
 * their place, which is the substitution §3.2 of the paper makes a
 * prerequisite rather than a refinement: a blackbox stores nothing, and
 * a register file that does not hold values fails CoreMark's CRCs
 * rather than quietly reporting low memory power.
 *
 * The shapes are not chosen here. They fall out of the configuration in
 * //test/coremark_joule/rtl/veer/config: a 16 kB instruction cache gives
 * ram_256x34 for its data and ram_64x21 for its tags, and a 64 kB DCCM
 * in eight banks gives ram_2048x39. The 16 kB size was picked because
 * these three are exactly what ASAP7 already has.
 *
 * Follows the shape of ORFS's own asap7/swerv_wrapper/macros.v, which
 * does the same job for the same core.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
/* The macros themselves, as blackboxes.
 *
 * Yosys would take these from the Liberty views on its own, but the
 * slang frontend elaborates the whole design first and a module it has
 * never seen is a hard error there rather than an implicit blackbox. The
 * port lists match the Liberty exactly -- clk, ce_in, we_in, addr_in,
 * wd_in, rd_out -- so a mismatch fails here rather than turning into a
 * silently unconnected macro pin.
 */
(* blackbox *)
module fakeram7_2048x39 (clk, ce_in, we_in, addr_in, wd_in, rd_out);
   input         clk, ce_in, we_in;
   input  [10:0] addr_in;
   input  [38:0] wd_in;
   output [38:0] rd_out;
endmodule

(* blackbox *)
module fakeram7_256x34 (clk, ce_in, we_in, addr_in, wd_in, rd_out);
   input        clk, ce_in, we_in;
   input  [7:0] addr_in;
   input [33:0] wd_in;
   output [33:0] rd_out;
endmodule

(* blackbox *)
module fakeram7_64x21 (clk, ce_in, we_in, addr_in, wd_in, rd_out);
   input        clk, ce_in, we_in;
   input  [5:0] addr_in;
   input [20:0] wd_in;
   output [20:0] rd_out;
endmodule

module ram_2048x39 (CLK, ADR, D, Q, WE);
   input         CLK, WE;
   input  [10:0] ADR;
   input  [38:0] D;
   output [38:0] Q;

   fakeram7_2048x39 mem (
      .clk     (CLK),
      .rd_out  (Q),
      .ce_in   (1'b1),
      .we_in   (WE),
      .addr_in (ADR),
      .wd_in   (D)
   );
endmodule

module ram_256x34 (CLK, ADR, D, Q, WE);
   input        CLK, WE;
   input  [7:0] ADR;
   input [33:0] D;
   output [33:0] Q;

   fakeram7_256x34 mem (
      .clk     (CLK),
      .rd_out  (Q),
      .ce_in   (1'b1),
      .we_in   (WE),
      .addr_in (ADR),
      .wd_in   (D)
   );
endmodule

module ram_64x21 (CLK, ADR, D, Q, WE);
   input        CLK, WE;
   input  [5:0] ADR;
   input [20:0] D;
   output [20:0] Q;

   fakeram7_64x21 mem (
      .clk     (CLK),
      .rd_out  (Q),
      .ce_in   (1'b1),
      .we_in   (WE),
      .addr_in (ADR),
      .wd_in   (D)
   );
endmodule
