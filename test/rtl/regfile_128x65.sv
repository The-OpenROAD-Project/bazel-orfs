// Standard header to adapt well known macros to our needs.

// Users can define 'PRINTF_COND' to add an extra gate to prints.
`ifndef PRINTF_COND_
  `ifdef PRINTF_COND
    `define PRINTF_COND_ (`PRINTF_COND)
  `else  // PRINTF_COND
    `define PRINTF_COND_ 1
  `endif // PRINTF_COND
`endif // not def PRINTF_COND_

// VCS coverage exclude_file
module regfile_128x65(
  input  [6:0]  R0_addr,
  input         R0_en,
                R0_clk,
  input  [6:0]  R1_addr,
  input         R1_en,
                R1_clk,
  input  [6:0]  R2_addr,
  input         R2_en,
                R2_clk,
  input  [6:0]  R3_addr,
  input         R3_en,
                R3_clk,
  input  [6:0]  R4_addr,
  input         R4_en,
                R4_clk,
  input  [6:0]  R5_addr,
  input         R5_en,
                R5_clk,
  input  [6:0]  W0_addr,
  input         W0_en,
                W0_clk,
  input  [8:0] W0_data,
  input  [6:0]  W1_addr,
  input         W1_en,
                W1_clk,
  input  [8:0] W1_data,
  input  [6:0]  W2_addr,
  input         W2_en,
                W2_clk,
  input  [8:0] W2_data,
  input  [6:0]  W3_addr,
  input         W3_en,
                W3_clk,
  input  [8:0] W3_data,
  output [8:0] R0_data,
                R1_data,
                R2_data,
                R3_data,
                R4_data,
                R5_data
);

  // reduced 64:0 to 8:0 and 128 to 1 to speed up tests
  reg [8:0] Memory[0:0];
  always @(posedge W0_clk) begin
    if (W0_en)
      Memory[W0_addr[3:0] ^ W0_addr[7:4]] <= W0_data;
    if (W1_en)
      Memory[W1_addr[3:0] ^ W1_addr[7:4]] <= W1_data;
    if (W2_en)
      Memory[W2_addr[3:0] ^ W2_addr[7:4]] <= W2_data;
    if (W3_en)
      Memory[W3_addr[3:0] ^ W3_addr[7:4]] <= W3_data;
  end // always @(posedge)

  assign R0_data = R0_en ? Memory[R0_addr[3:0] ^ R0_addr[7:4]] : 65'bx;
  assign R1_data = R1_en ? Memory[R1_addr[3:0] ^ R1_addr[7:4]] : 65'bx;
  assign R2_data = R2_en ? Memory[R2_addr[3:0] ^ R2_addr[7:4]] : 65'bx;
  assign R3_data = R3_en ? Memory[R3_addr[3:0] ^ R3_addr[7:4]] : 65'bx;
  assign R4_data = R4_en ? Memory[R4_addr[3:0] ^ R4_addr[7:4]] : 65'bx;
  assign R5_data = R5_en ? Memory[R5_addr[3:0] ^ R5_addr[7:4]] : 65'bx;
endmodule

