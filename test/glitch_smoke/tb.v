// Drive `a` high once and count what `y` does. With zero delay `y`
// never leaves 0; with the SDF annotated it emits a pulse the logic
// function forbids. That pulse is glitch power in its smallest possible
// form (paper, 5.2).
//
// The count is printed rather than dumped, so this can be a test rather
// than a waveform somebody looks at. A dump is still available with
// +vcd=<file> when somebody does want to look.
//
// Note -gspecify on the iverilog command line: without it the specify
// blocks are dropped and $sdf_annotate is skipped with a warning, which
// would leave a zero-delay run masquerading as an annotated one.
module tb;
   reg a = 0;
   wire y;
   integer pulses = 0;
   time high_time = 0, last = 0;
   reg prev = 1'bx;
   reg [1023:0] vcdfile, sdffile;

   glitch_top dut (.a(a), .y(y));

   // How long `y` spends at 1, which its logic function forbids
   // entirely -- not how many times it gets there.
   //
   // The distinction is the measurement. An event-driven simulator
   // evaluates zero-delay gates in delta cycles, so a reconvergent path
   // reaches 1 and returns in the *same* instant even with no delays at
   // all: a count sees that as a pulse, a VCD does not record it, and
   // it carries no energy because nothing ever charged. A pulse with
   // width is the thing that costs power, and only annotated delays
   // produce one.
   always @(y) begin
      if (prev === 1'b1) high_time = high_time + ($time - last);
      prev = y;
      last = $time;
      if (y === 1'b1) pulses = pulses + 1;
   end

   initial begin
      if ($value$plusargs("sdf=%s", sdffile)) $sdf_annotate(sdffile, dut);
      if ($value$plusargs("vcd=%s", vcdfile)) begin
         $dumpfile(vcdfile);
         $dumpvars(0, tb);
      end
      #1000 a = 1;
      #1000 a = 0;
      #1000;
      $display("glitch_smoke: %0d pulse(s) on y, %0d time unit(s) high",
               pulses, high_time);
      $finish;
   end
endmodule
