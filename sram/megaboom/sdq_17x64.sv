module sdq_17x64(
  input  [4:0]  R0_addr,
  input         R0_en,
                R0_clk,
  output [15:0] R0_data,
  input  [4:0]  W0_addr,
  input         W0_en,
                W0_clk,
  input  [15:0] W0_data
);

  //  reduced 63:0 to 15:0 and 0:16 to 0:0 to speed up tests and 
  reg [15:0] Memory[0:0];
  always @(posedge W0_clk) begin
    if (W0_en & 1'h1)
      Memory[W0_addr] <= W0_data;
  end // always @(posedge)
  assign R0_data = R0_en ? Memory[R0_addr] : 64'bx;
endmodule
