// The positive control of the retiming study: a W x W multiplier whose
// pipeline registers all sit in front of it. a and b are registered at
// the ports, delayed by STAGES more registers with no logic between
// them, multiplied, and the product registered at the output port. Every
// cycle but the last is empty, so the period is the whole multiplier;
// sliding the STAGES registers forward into it, which is what retime
// does, can divide it by up to STAGES + 1. The port registers stay where
// they are: retime never moves a register on a port's net.
module pipe_mult #(
    parameter int W = 32,
    parameter int STAGES = 3,
    // 1: an inverter between each input port and its first register, so
    // no register sits on a port's net.
    parameter bit INVERT_IN = 0
) (
    input logic clk,
    input logic [W-1:0] a,
    input logic [W-1:0] b,
    output logic [2*W-1:0] p
);
  logic [W-1:0] a_q[STAGES+1];
  logic [W-1:0] b_q[STAGES+1];
  always_ff @(posedge clk) begin
    a_q[0] <= INVERT_IN ? ~a : a;
    b_q[0] <= INVERT_IN ? ~b : b;
    for (int i = 1; i <= STAGES; i++) begin
      a_q[i] <= a_q[i-1];
      b_q[i] <= b_q[i-1];
    end
    p <= a_q[STAGES] * b_q[STAGES];
  end
endmodule
