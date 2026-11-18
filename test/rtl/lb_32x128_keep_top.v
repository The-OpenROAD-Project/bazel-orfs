// A top over lb_32x128_top, so that lb_32x128_top can be a kept module
// with the macro lb_32x128 inside it (lb_32x128_keep_top in test/BUILD).
module lb_32x128_keep_top(
  input  [4:0] R0_addr,
  input        R0_en,
               R0_clk,
  output [7:0] R0_data,
  input  [4:0] W0_addr,
  input        W0_en,
               W0_clk,
  input  [7:0] W0_data
);
  lb_32x128_top u_top (
    .R0_addr(R0_addr),
    .R0_en(R0_en),
    .R0_clk(R0_clk),
    .R0_data(R0_data),
    .W0_addr(W0_addr),
    .W0_en(W0_en),
    .W0_clk(W0_clk),
    .W0_data(W0_data)
  );
endmodule
