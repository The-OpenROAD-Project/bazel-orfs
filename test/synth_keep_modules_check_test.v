// Fixture for synth_keep_modules_check_test.tcl.
//
// Module names mimic a name-mangling pattern (`ClassName$instance.path`) and a
// plain top so the test can probe both shapes that the kept-modules pattern
// in synth.tcl / synth_keep.tcl has to recognise.

module \FooKept$top.foo (input a, output b);
  assign b = a;
endmodule

module \BarKept$top.bar (input a, output b);
  assign b = ~a;
endmodule

module Unrelated(input a, output b);
  assign b = a;
endmodule

module Top(input a, output b);
  wire w;
  \FooKept$top.foo foo(.a(a), .b(w));
  \BarKept$top.bar bar(.a(w), .b(b));
endmodule
