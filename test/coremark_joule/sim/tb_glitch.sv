/* Timing-annotated gate-level testbench, for glitch power (5.2).
 *
 * The study's own harness is C++ against Verilator, which cannot do
 * this job: it parses $sdf_annotate and specify blocks and discards
 * them, because evaluating a cycle as compiled straight-line code is
 * exactly what throws intra-cycle ordering away. A glitch only exists
 * when two inputs arrive at different times, so it needs an
 * event-driven simulator and back-annotated delays.
 *
 * This is deliberately not a replacement for that harness. It runs a
 * *window*, not a benchmark: a full CoreMark iteration under timing
 * annotation would produce a VCD of hundreds of gigabytes (5.2), so
 * what is measured is the toggle count over a few thousand cycles with
 * delays against the same window without them. The quantity that comes
 * out is a ratio, not a power.
 *
 * Plusargs:
 *   +meminit=<hex>    the memory image, as cm_soc requires
 *   +sdf=<file>       annotate delays; omitted, this is the zero-delay arm
 *   +vcd=<file>       where to dump
 *   +cycles=<n>       window length, in clock cycles
 *   +skip=<n>         cycles to run before dumping starts
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`timescale 1ps / 1ps

/* The instance of the hardened design inside cm_soc. Every SoC but
 * VeeR's calls it `cpu`; VeeR's calls it `rvtop`, and six saif_scope
 * entries name it, so the testbench bends rather than the flow.
 * $sdf_annotate and $dumpvars both take a static hierarchical name, so
 * this cannot be a plusarg. */
`ifndef CPU_INST
`define CPU_INST cpu
`endif

module tb_glitch;
  localparam int unsigned PeriodPs = 1282;

  logic clk = 1'b0;
  logic resetn = 1'b0;
  logic trap, out_valid, halt_valid;
  logic [7:0] out_byte;
  logic [31:0] dbg_instr_addr;

  cm_soc dut (
      .clk(clk),
      .resetn(resetn),
      .trap(trap),
      .out_valid(out_valid),
      .out_byte(out_byte),
      .halt_valid(halt_valid),
      .dbg_instr_addr(dbg_instr_addr)
  );

  always #(PeriodPs / 2) clk = ~clk;

  string sdf_file, vcd_file;
  int unsigned cycles, skip, n;

  initial begin
    /* Annotation first, before any edge: a delay that arrives after the
     * design has started is a delay that did not apply to what came
     * before it. The scope is the design instance, because every
     * INSTANCE path in the SDF is relative to it, and write_sdf names
     * them from the hardened design (cmj_ibex) rather than from the
     * testbench -- a mismatch reports
     * "Unable to find ... in scope" rather than quietly annotating
     * nothing. */
    if ($value$plusargs("sdf=%s", sdf_file)) $sdf_annotate(sdf_file, dut.`CPU_INST);

    if (!$value$plusargs("vcd=%s", vcd_file)) vcd_file = "glitch.vcd";
    if (!$value$plusargs("cycles=%d", cycles)) cycles = 2000;
    if (!$value$plusargs("skip=%d", skip)) skip = 200;

    /* Reset long enough for the netlist's state to be defined. In a
     * 4-state simulator every flop starts X, and anything reset does
     * not reach stays X -- which is the way this measurement fails, if
     * it fails. */
    /* Released on a negedge, deliberately. Changing an asynchronous
     * reset on the same edge the flops capture is a race: with zero
     * delay the simulator's event ordering resolves it silently, and
     * with annotated delays it resolves into X across the whole
     * netlist, which looks like the design failing to initialise
     * rather than like a testbench that drove a signal at the wrong
     * moment. */
    /* Asserted *after* annotation, not at declaration. A module path
     * delay holds its output at X until its input first transitions,
     * so a buffer on the reset net that is already at its final value
     * when $sdf_annotate runs feeds X to every flop it reaches -- for
     * the whole reset window, which is exactly when the design needs a
     * clean level. Driving the edge here gives every such path an event
     * to propagate. */
    #(PeriodPs / 4) resetn = 1'b0;
    repeat (20) @(negedge clk);
    #(PeriodPs / 4) resetn = 1'b1;

    repeat (skip) @(posedge clk);

    $dumpfile(vcd_file);
    /* +mult dumps only the multiplier subtree. A whole-core dump is
     * tens of megabytes per hundred cycles, and finding the cycles in
     * which the multiplier actually works means running far longer than
     * that allows: CoreMark dispatches its matrix work per list item
     * (calc_func), so it arrives in short bursts rather than as a
     * phase. */
    /* +cpu dumps the whole hardened design, which is how a boundary is
     * recorded for a unit that has no scope of its own. $dumpvars takes
     * a static hierarchical name, so a scope cannot be chosen by string
     * at run time; dumping the design once and cutting each unit's
     * ports out of that one file afterwards is what scales to a sweep,
     * and is the only way to reach a unit instantiated more than once
     * -- VeeR has four of the same ALU. */
`ifdef IBEX_MULT_SCOPE
    if ($test$plusargs("mult")) begin
      $dumpvars(0, tb_glitch.dut.cpu.\u_core__dot__u_ibex_core__dot__ex_block_i .\gen_multdiv_fast__dot__multdiv_i );
    end else
`endif
    if ($test$plusargs("cpu")) begin
      $dumpvars(0, tb_glitch.dut.`CPU_INST);
    end else begin
      $dumpvars(0, tb_glitch);
    end
    for (n = 0; n < cycles; n++) @(posedge clk);
    $display("tb_glitch: dumped %0d cycles at %0d ps%s", cycles, PeriodPs,
             sdf_file != "" ? " (SDF annotated)" : " (zero delay)");
    $finish;
  end
endmodule
