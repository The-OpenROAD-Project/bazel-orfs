// Drive `a` high once and dump. With zero delay `y` never leaves 0;
// with the SDF annotated it emits a pulse the logic function forbids.
//
// Note -gspecify on the iverilog command line: without it the specify
// blocks are dropped and $sdf_annotate is skipped with a warning, which
// would leave a zero-delay run masquerading as an annotated one.
module tb;
   reg a = 0;
   wire y;
   reg [1023:0] vcdfile;
   glitch_top dut (.a(a), .y(y));

   initial begin
      if ($test$plusargs("sdf")) $sdf_annotate("test/glitch_smoke/glitch.sdf", dut);
      if (!$value$plusargs("vcd=%s", vcdfile)) vcdfile = "dump.vcd";
      $dumpfile(vcdfile);
      $dumpvars(0, tb);
      #1000 a = 1;
      #1000 a = 0;
      #1000 $finish;
   end
endmodule
