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
// Reduced from 6R/4W 9-bit to 2R/1W 4-bit to speed up CI builds.
// Still tests the full ORFS flow (synth through final) with IO constraints.
module regfile_128x65(
  input  [6:0]  R0_addr,
  input         R0_en,
                R0_clk,
  input  [6:0]  R1_addr,
  input         R1_en,
                R1_clk,
  input  [6:0]  W0_addr,
  input         W0_en,
                W0_clk,
  input  [3:0]  W0_data,
  output [3:0]  R0_data,
                R1_data
);

  reg [3:0] Memory[0:0];
  always @(posedge W0_clk) begin
    if (W0_en)
      Memory[0] <= W0_data;
  end // always @(posedge)

  assign R0_data = R0_en ? Memory[0] : 4'bx;
  assign R1_data = R1_en ? Memory[0] : 4'bx;
endmodule

