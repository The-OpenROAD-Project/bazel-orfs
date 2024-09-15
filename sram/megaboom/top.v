module top(
  input         clock,
  input  [4:0]  R0_addr,
  input         R0_en,
  output [63:0] R0_data,
  input  [4:0]  W0_addr,
  input         W0_en,
  input  [63:0] W0_data
);
  sdq_17x64 u_sdq_17x64 (
    .R0_addr(R0_addr),
    .R0_en(R0_en),
    .R0_clk(clock),       // Use the same clock for read
    .R0_data(R0_data),
    .W0_addr(W0_addr),
    .W0_en(W0_en),
    .W0_clk(clock),       // Use the same clock for write
    .W0_data(W0_data)
  );

endmodule
