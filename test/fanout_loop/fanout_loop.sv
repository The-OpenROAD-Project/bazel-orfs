// The smallest shape of XiangShan's decode-buffer loops (ideas entry 55):
// a register that loops back to itself through one gate on the same net
// that drives 64 other sinks. asap7's flops have only QN, so v is an
// inverter on QN, and that inverter's net feeds the loop's AND and the 64
// data ANDs: fanout 65, over a cap of 32, so the flow buffers the net.
// The correct result, by hand: v's loop is flop -> INV -> AND -> flop, with
// no buffer on it; the 64 data ANDs hang off a buffer tree beside it.
module fanout_loop (
    input  logic        clk,
    input  logic        in0,
    input  logic [63:0] in,
    output logic        v_out,
    output logic [63:0] d_out
);
  logic        v;
  logic [63:0] d;
  always_ff @(posedge clk) begin
    v <= v & in0;
    d <= in & {64{v}};
  end
  assign v_out = v;
  assign d_out = d;
endmodule
