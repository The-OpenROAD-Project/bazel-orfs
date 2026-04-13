module dummy(input clk, input d, output q);
  reg q_reg;
  always @(posedge clk) q_reg <= d;
  assign q = q_reg;
endmodule
