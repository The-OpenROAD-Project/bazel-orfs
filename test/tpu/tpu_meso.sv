// tpu in its rig: the surroundings it needs to be built realistically,
// without cheating. tpu is mesochronous with what drives it, the same
// clock at a phase of its own, so a mesochronous FIFO stands on each side
// of it (meso_fifo.sv), on tpu's one clock: what comes from the pins is
// written on a short branch of the clock tree, and tpu's logic, deep in
// the macros' trees, reads it. Every path of tpu then starts and ends at
// a register on that clock.
//
// The interface is tpu's own, which is already flow control without
// back-pressure: valid in (a_valid, w_valid), valid out (c_valid), and
// no ready either way. tpu takes a cycle with neither valid anywhere in a
// stream: a row of A is independent of the others, a gap in a weight
// load is a cycle of computing on zeros. So the input FIFO forwards a
// word whenever it has one and a cycle without is such a bubble. Results
// are tagged by c_valid, not counted in cycles: the FIFOs add four cycles
// of latency to tpu's 2N-1. tpu's module is unchanged.
module tpu_meso #(
    parameter int N     = 8,
    parameter int DW    = 8,
    parameter int ACCW  = 32,
    parameter int DEPTH = 2
) (
    input  logic              clk,
    input  logic              rst,
    input  logic              w_valid,
    input  logic [  N*DW-1:0] w_data,
    input  logic              a_valid,
    input  logic [  N*DW-1:0] a_data,
    output logic              c_valid,
    output logic [N*ACCW-1:0] c_data
);
  // reset, registered once at the pins: its fan-out to every register in
  // tpu is then a path from a register like any other. The input FIFO,
  // which faces the pins, takes the pin's own: a word that comes the
  // cycle reset falls would otherwise be dropped.
  logic rst_q;
  always_ff @(posedge clk) rst_q <= rst;

  // one word per cycle with either valid, weights and activations in the
  // order they came
  localparam int IW = 2 + 2 * N * DW;
  logic in_valid;
  logic [IW-1:0] in_bits;
  meso_fifo #(
      .WIDTH(IW),
      .DEPTH(DEPTH)
  ) u_in (
      .clock(clk),
      .reset(rst),
      .enq_valid(w_valid || a_valid),
      .enq_bits({w_valid, w_data, a_valid, a_data}),
      .deq_valid(in_valid),
      .deq_bits(in_bits),
      .overflow()
  );

  logic t_w_valid, t_a_valid, t_c_valid;
  logic [N*DW-1:0] t_w_data, t_a_data;
  logic [N*ACCW-1:0] t_c_data;
  assign {t_w_valid, t_w_data, t_a_valid, t_a_data} = in_bits;

  tpu #(
      .N(N),
      .DW(DW),
      .ACCW(ACCW)
  ) u_tpu (
      .clk(clk),
      .rst(rst_q),
      .w_valid(in_valid && t_w_valid),
      .w_data(t_w_data),
      .a_valid(in_valid && t_a_valid),
      .a_data(t_a_data),
      .c_valid(t_c_valid),
      .c_data(t_c_data)
  );

  meso_fifo #(
      .WIDTH(N * ACCW),
      .DEPTH(DEPTH)
  ) u_out (
      .clock(clk),
      .reset(rst_q),
      .enq_valid(t_c_valid),
      .enq_bits(t_c_data),
      .deq_valid(c_valid),
      .deq_bits(c_data),
      .overflow()
  );
endmodule
