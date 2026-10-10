// Two white boxes of different shapes under one parent: the smallest
// design whose holes (the boxes' logic write_xaiger2 embeds in the
// .xaig) have more than one output wire, so their order matters.
module big (
    input  a,
    input  b,
    input  c,
    output y
);
  assign y = (a & b) | c;
endmodule

module small (
    input  a,
    output y
);
  assign y = ~a;
endmodule

module top (
    input  a,
    input  b,
    input  c,
    input  d,
    output y,
    output z
);
  big u1 (
      .a(a),
      .b(b),
      .c(c),
      .y(y)
  );
  small u2 (
      .a(d),
      .y(z)
  );
endmodule
