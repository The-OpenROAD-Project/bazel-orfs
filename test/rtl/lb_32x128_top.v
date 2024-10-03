// mock version for fast builds
module lb_32x128_top(
  input  [4:0]   R0_addr,
  input          R0_en,
                 R0_clk,
  output [127:0] R0_data,
  input  [4:0]   W0_addr,
  input          W0_en,
                 W0_clk,
  input  [127:0] W0_data
);
    lb_32x128 lb_32x128_inst (
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

