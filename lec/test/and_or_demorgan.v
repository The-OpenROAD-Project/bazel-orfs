// The same function through De Morgan: equivalent to and_or.v.
module and_or(input a, input b, input c, output y);
  assign y = ~(~(a & b) & ~c);
endmodule
