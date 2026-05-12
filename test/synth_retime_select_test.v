// Fixture for synth_retime_select_test.tcl.
//
// Module names mimic a name-mangling pattern (`ClassName$instance.path`) so
// the select globs in the test match the kind of names downstream synthesis
// flows feed to SYNTH_RETIME_MODULES.

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
