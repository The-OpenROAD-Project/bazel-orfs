// generate_ram with two write ports, a plain read port and a banked one
// (-rb_ports 1) over 4 banks of 2 words: its behavioral model (RAM8x8)
// and its netlist (RAM8x8_gen) on the same inputs.
module tb_ram_rb (
    input        clk,
    input  [7:0] D0,
    input  [7:0] D1,
    input  [2:0] addr_w0,
    input  [2:0] addr_w1,
    input  [2:0] addr_r0,
    input        addr_rb0_b0,
    input        addr_rb0_b1,
    input        addr_rb0_b2,
    input        addr_rb0_b3,
    input        we0,
    input        we1,
    output [7:0] Q_model,
    output [7:0] Q_gen,
    output [31:0] Qrb_model,
    output [31:0] Qrb_gen
);
  RAM8x8 model (
      .clk(clk), .D0(D0), .D1(D1), .Q(Q_model), .addr_w0(addr_w0),
      .addr_w1(addr_w1), .addr_r0(addr_r0), .we0(we0), .we1(we1),
      .addr_rb0_b0(addr_rb0_b0), .addr_rb0_b1(addr_rb0_b1),
      .addr_rb0_b2(addr_rb0_b2), .addr_rb0_b3(addr_rb0_b3),
      .Qrb0_b0(Qrb_model[7:0]), .Qrb0_b1(Qrb_model[15:8]),
      .Qrb0_b2(Qrb_model[23:16]), .Qrb0_b3(Qrb_model[31:24])
  );
  RAM8x8_gen gen (
      .clk(clk), .D0(D0), .D1(D1), .Q(Q_gen), .addr_w0(addr_w0),
      .addr_w1(addr_w1), .addr_r0(addr_r0), .we0(we0), .we1(we1),
      .addr_rb0_b0(addr_rb0_b0), .addr_rb0_b1(addr_rb0_b1),
      .addr_rb0_b2(addr_rb0_b2), .addr_rb0_b3(addr_rb0_b3),
      .Qrb0_b0(Qrb_gen[7:0]), .Qrb0_b1(Qrb_gen[15:8]),
      .Qrb0_b2(Qrb_gen[23:16]), .Qrb0_b3(Qrb_gen[31:24])
  );
endmodule
