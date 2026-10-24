// A mesochronous FIFO on one clock: the shape of rocket-chip's async
// queue (ORFS's chi_async_bridge, async_queue_source.sv and
// async_queue_sink.sv), a write side, a memory and a read mux into a
// register on the read side, without its synchronisers. Both sides are on
// the same clock; what differs is where on its tree they sit, the write
// side on a short branch and the read side on a deep one, or the other
// way round. Static timing sees one clock with two insertion latencies
// and times every path between the sides, so the pointers cross as plain
// binary counters.
//
// No back-pressure: the read side pops whenever the FIFO is not empty,
// and the write side writes whenever enq_valid is high, at most one word
// a cycle each. A word written at one edge is read at the next and leaves
// at the one after, so no more than one word is ever waiting: DEPTH 2 is
// the maximum case, with a lap to spare. overflow says otherwise, for a
// simulation to check; nothing in hardware reads it.
module meso_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 2,
    localparam int BITS = $clog2(DEPTH)
) (
    input  logic             clock,
    input  logic             reset,
    input  logic             enq_valid,
    input  logic [WIDTH-1:0] enq_bits,
    output logic             deq_valid,
    output logic [WIDTH-1:0] deq_bits,
    output logic             overflow
);
  // the pointers carry a lap bit, so full and empty differ
  if (DEPTH < 2 || (DEPTH & (DEPTH - 1)) != 0) begin : depth_check
    $error("meso_fifo: DEPTH must be a power of 2 and at least 2");
  end

  // The write side.
  logic [BITS:0] widx;
  logic [WIDTH-1:0] mem[DEPTH];
  always_ff @(posedge clock) begin
    if (reset) begin
      widx <= '0;
    end else if (enq_valid) begin
      mem[widx[BITS-1:0]] <= enq_bits;
      widx <= widx + 1'b1;
    end
  end

  // The read side.
  logic [BITS:0] ridx;
  logic pop;
  assign pop = ridx != widx;
  always_ff @(posedge clock) begin
    if (reset) begin
      ridx <= '0;
      deq_valid <= 1'b0;
    end else begin
      deq_valid <= pop;
      if (pop) begin
        deq_bits <= mem[ridx[BITS-1:0]];
        ridx <= ridx + 1'b1;
      end
    end
  end

  // a write into a full FIFO: the write pointer a lap ahead
  assign overflow = enq_valid && widx[BITS-1:0] == ridx[BITS-1:0]
      && widx[BITS] != ridx[BITS];
endmodule
