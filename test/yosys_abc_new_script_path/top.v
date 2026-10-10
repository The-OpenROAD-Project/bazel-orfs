// Any small logic: the test is about which ABC script abc_new runs.
module top (
    input  [7:0] a,
    input  [7:0] b,
    output [7:0] y
);
  assign y = (a & b) ^ (a | ~b);
endmodule
