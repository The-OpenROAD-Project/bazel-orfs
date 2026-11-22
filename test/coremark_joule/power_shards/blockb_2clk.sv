// BlockB of test/planned_parent's blocks.sv as its flow builds it: the
// one clock split into two ports, `clock` and `clock_ext`, as a flow can
// (the SDC puts the one clock on both, constraints_2clk.sdc). The SoC's
// RTL keeps blocks.sv's BlockB with its one clock port, so a simulation
// that mixes this block's netlist with RTL meets a port it must bridge.
module BlockB (
    input clock,
    input clock_ext,
    input [159:0] din,
    output [159:0] dout,
    input [15:0] ext_in,
    output [15:0] ext_out
);
  reg [159:0] din_r;
  reg [159:0] dout_r;
  always @(posedge clock) begin
    din_r <= din;
    dout_r <= {din_r[158:0], din_r[159]} ^ din_r;
  end
  assign dout = dout_r;
  reg [15:0] ext_r;
  always @(posedge clock_ext) ext_r <= ext_in ^ din_r[15:0];
  assign ext_out = ext_r;
endmodule
