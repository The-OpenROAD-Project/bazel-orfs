// mock version for fast builds
module lb_32x128(
  input  [4:0]   R0_addr,
  input          R0_en,
                 R0_clk,
  output [7:0] R0_data,
  input  [4:0]   W0_addr,
  input          W0_en,
                 W0_clk,
  input  [7:0] W0_data
);

  reg [3:0] Memory[0:0]; // Reduced rows to 1 and 8 bits
  always @(posedge W0_clk) begin
    if (W0_en & 1'h1)
      Memory[W0_addr[4:3] ^ W0_addr[1:0]] <= W0_data; // XORing high and low bits
  end // always @(posedge)
  assign R0_data = R0_en ? Memory[R0_addr[4:3] ^ R0_addr[1:0]] : 128'bx; // XORing high and low bits
endmodule

