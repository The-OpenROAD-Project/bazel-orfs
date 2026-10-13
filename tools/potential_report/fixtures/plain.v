// Plain control logic: no repetition, nothing to report.
module Plain(input clock, input [7:0] a, input [7:0] b, input sel,
             output reg [7:0] q);
  always @(posedge clock) q <= sel ? a + b : a ^ b;
endmodule
