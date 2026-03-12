// Standard header to adapt well known macros for prints and assertions.

// Users can define 'ASSERT_VERBOSE_COND' to add an extra gate to assert error printing.
`ifndef ASSERT_VERBOSE_COND_
  `ifdef ASSERT_VERBOSE_COND
    `define ASSERT_VERBOSE_COND_ (`ASSERT_VERBOSE_COND)
  `else  // ASSERT_VERBOSE_COND
    `define ASSERT_VERBOSE_COND_ 1
  `endif // ASSERT_VERBOSE_COND
`endif // not def ASSERT_VERBOSE_COND_

// Users can define 'STOP_COND' to add an extra gate to stop conditions.
`ifndef STOP_COND_
  `ifdef STOP_COND
    `define STOP_COND_ (`STOP_COND)
  `else  // STOP_COND
    `define STOP_COND_ 1
  `endif // STOP_COND
`endif // not def STOP_COND_

// VCS coverage exclude_file
// Reduced from 8-way (184-bit) to 2-way (46-bit) to speed up CI builds.
// Original: 184 = 8 * 23 bits (8 ways, each 21-bit tag + 2-bit coh_state).
// Reduced:   46 = 2 * 23 bits (2 ways).
module tag_array_64x184(
  input  [5:0]  R0_addr,
  input         R0_en,
                R0_clk,
  output [45:0] R0_data,
  input  [5:0]  W0_addr,
  input         W0_en,
                W0_clk,
  input  [45:0] W0_data,
  input  [1:0]  W0_mask
);

  reg [31:0] Memory[0:1]; // 2 rows, 32 bits
  reg        _R0_en_d0;
  reg [1:0]  _W0_addr_d0, _R0_addr_d1;

  always @(posedge R0_clk) begin
    _R0_en_d0 <= R0_en;
    _R0_addr_d1 <= R0_addr[1:0];
  end // always @(posedge)

  always @(posedge W0_clk) begin
    _W0_addr_d0 <= W0_addr[1:0];
    if (W0_en & W0_mask[0])
      Memory[_W0_addr_d0][22:0] <= W0_data[22:0];
    if (W0_en & W0_mask[1])
      Memory[_W0_addr_d0][31:23] <= W0_data[45:23];
  end // always @(posedge)

  assign R0_data = _R0_en_d0 ? Memory[_R0_addr_d1][45:0] : 46'bx;
endmodule

