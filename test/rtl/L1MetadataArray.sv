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

// Reduced from 8-way to 2-way to speed up CI builds.
// Still tests hierarchical synthesis (L1MetadataArray instantiates tag_array_64x184).
module L1MetadataArray(
  input         clock,
                reset,
  output        io_read_ready,
  input         io_read_valid,
  input  [5:0]  io_read_bits_idx,
  output        io_write_ready,
  input         io_write_valid,
  input  [5:0]  io_write_bits_idx,
  input  [1:0]  io_write_bits_way_en,
  input  [1:0]  io_write_bits_data_coh_state,
  input  [20:0] io_write_bits_data_tag,
  output [1:0]  io_resp_0_coh_state,
  output [20:0] io_resp_0_tag,
  output [1:0]  io_resp_1_coh_state,
  output [20:0] io_resp_1_tag
);

  wire [45:0] _tag_array_ext_R0_data;
  reg  [6:0]   rst_cnt;
  wire [1:0]   _wdata_T_coh_state = rst_cnt[6] ? io_write_bits_data_coh_state : 2'h0;
  wire [20:0]  _wdata_T_tag = rst_cnt[6] ? io_write_bits_data_tag : 21'h0;
  wire         tag_array_MPORT_en = ~(rst_cnt[6]) | io_write_valid;
  always @(posedge clock) begin
    if (reset)
      rst_cnt <= 7'h0;
    else if (rst_cnt[6]) begin
    end
    else
      rst_cnt <= rst_cnt + 7'h1;
  end // always @(posedge)
  tag_array_64x184 tag_array_ext (
    .R0_addr (io_read_bits_idx),
    .R0_en   (~tag_array_MPORT_en & io_read_valid),
    .R0_clk  (clock),
    .R0_data (_tag_array_ext_R0_data),
    .W0_addr (rst_cnt[6] ? io_write_bits_idx : rst_cnt[5:0]),
    .W0_en   (tag_array_MPORT_en),
    .W0_clk  (clock),
    .W0_data ({_wdata_T_coh_state, _wdata_T_tag, _wdata_T_coh_state, _wdata_T_tag}),
    .W0_mask (rst_cnt[6] ? io_write_bits_way_en : 2'b11)
  );
  assign io_read_ready = ~tag_array_MPORT_en;
  assign io_write_ready = rst_cnt[6];
  assign io_resp_0_coh_state = _tag_array_ext_R0_data[22:21];
  assign io_resp_0_tag = _tag_array_ext_R0_data[20:0];
  assign io_resp_1_coh_state = _tag_array_ext_R0_data[45:44];
  assign io_resp_1_tag = _tag_array_ext_R0_data[43:23];
endmodule

