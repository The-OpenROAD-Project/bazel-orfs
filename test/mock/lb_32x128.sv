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

  reg [7:0] Memory[0:0];
  reg [7:0] R0_data_reg;

  always @(posedge W0_clk) begin
    Memory[W0_addr[4:3] ^ W0_addr[1:0]] <= W0_data;
  end

  always @(posedge R0_clk) begin
    R0_data_reg <= Memory[R0_addr[4:3] ^ R0_addr[1:0]];
  end

  assign R0_data = R0_data_reg;
endmodule

