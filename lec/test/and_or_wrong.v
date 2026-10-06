// (a | b) | c: differs from and_or.v when exactly one of a, b is 1.
module and_or(input a, input b, input c, output y);
  assign y = (a | b) | c;
endmodule
