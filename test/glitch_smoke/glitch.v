// Two paths of unequal delay reconverging on one gate: the textbook
// glitch, and the smallest design that can have one.
//
// `a` feeds the AND directly and through an inverter, so `y` is
// permanently 0 by function. With zero delay that is all a simulator
// ever sees. Give the inverter a delay and the AND briefly sees
// (a=1, nota=1) after a rises, and emits a pulse that the logic says
// cannot exist. That pulse is glitch power: it charges a real
// capacitance and is invisible to a cycle-based simulator.
//
// The specify blocks carry zero delays on purpose. $sdf_annotate
// overwrites them, so a model only has to *declare* the path -- which
// is precisely what our generated standard-cell models do not do yet.
module INV_t (input A, output Y);
   assign Y = ~A;
   specify
      (A => Y) = 0;
   endspecify
endmodule

module AND_t (input A, input B, output Y);
   assign Y = A & B;
   specify
      (A => Y) = 0;
      (B => Y) = 0;
   endspecify
endmodule

module glitch_top (input a, output y);
   wire nota;
   INV_t u_inv (.A(a), .Y(nota));
   AND_t u_and (.A(a), .B(nota), .Y(y));
endmodule
