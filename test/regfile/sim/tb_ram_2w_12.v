// generate_ram with two write ports and one read port: its behavioral
// model (RAM8x8) and its netlist (RAM8x8_gen) on the same inputs.
module tb_ram_2w (
    input        clk,
    input  [7:0] D0,
    input  [7:0] D1,
    input  [3:0] addr_w0,
    input  [3:0] addr_w1,
    input  [3:0] addr_r0,
    input        we0,
    input        we1,
    output [7:0] Q_model,
    output [7:0] Q_gen
);
  RAM8x8 model (
      .clk(clk), .D0(D0), .D1(D1), .Q(Q_model), .addr_w0(addr_w0),
      .addr_w1(addr_w1), .addr_r0(addr_r0), .we0(we0), .we1(we1)
  );
  RAM8x8_gen gen (
      .clk(clk), .D0(D0), .D1(D1), .Q(Q_gen), .addr_w0(addr_w0),
      .addr_w1(addr_w1), .addr_r0(addr_r0), .we0(we0), .we1(we1)
  );
endmodule
