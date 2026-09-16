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
    if ($value$plusargs("sdf=%s", sdf_file)) $sdf_annotate(sdf_file, dut.cpu);

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
    repeat (20) @(negedge clk);
    resetn = 1'b1;

    repeat (skip) @(posedge clk);

    $dumpfile(vcd_file);
    $dumpvars(0, tb_glitch);
    for (n = 0; n < cycles; n++) @(posedge clk);
    $display("tb_glitch: dumped %0d cycles at %0d ps%s", cycles, PeriodPs,
             sdf_file != "" ? " (SDF annotated)" : " (zero delay)");
    $finish;
  end
endmodule
