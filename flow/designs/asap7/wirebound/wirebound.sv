// wirebound -- a wire-delay-dominated, congestion-bound asap7 microbenchmark.
//
// Why this design exists
// ---------------------
// ORFS's asap7 designs are all cell-delay dominated: asap7 cells are so
// small that a design of a few tens of thousands of instances fits in a
// die well under 100um, where an average net is short enough that gate
// delay sets the period. The pre-route timing estimate is then roughly
// right, because mispricing a short wire costs little.
//
// The regime this design targets is the opposite one, and ORFS has no
// design in it: routing demand large enough to want the top of the metal
// stack, spans long enough that wire R -- which varies ~8x from M1 to M9
// on asap7 -- sets the period, and enough contention that global place
// cannot make the problem go away. That is where `clk_period - WNS` read
// before routing stops agreeing with what routing achieves.
//
// Shape
// -----
// GROUPS register groups of WIDTH bits. Every group's next value is the
// XOR of FANIN other groups, each rotated by a different amount. Two
// properties are deliberate:
//
//   * The fan-in set is scattered, not a neighbourhood. STRIDE_I and
//     STRIDE_K are odd and mutually prime with the group count, so no
//     placement can cluster a group with the groups it reads. The
//     inter-group nets therefore stay die-crossing however the placer
//     folds the design -- the wire length is a property of the netlist,
//     not of one placement.
//   * The reduction is a balanced XOR tree (`^col`), not a chain, so
//     logic depth is log2(FANIN) -- four levels. Cell delay stays small
//     while the wires stay long, which is what makes the period a wire
//     measurement instead of a gate measurement.
//
// Nothing else is in here. No macros, no SRAM, no second clock domain,
// no hierarchy: each of those would be a confound for the thing being
// measured, and each is separately represented elsewhere in ORFS.
//
// Size is set by GROUPS, overridable with -DWIREBOUND_GROUPS.
//
// The default is measured, not chosen. Instance count grows as
// GROUPS * WIDTH * FANIN while die extent grows only as its square root,
// and the flow's cost grows faster than the instance count: 32 -> 64
// groups is 1.9x the cells and 3.1x the wall time (309s -> 967s through
// global route). Buying wire length by adding instances therefore costs
// roughly the square of what it buys, and utilization is the cheap axis
// instead -- see config.mk.
//
// 32 keeps synthesis through global route in the low hundreds of seconds
// and the whole calibration loop, which needs detailed route and two
// extractions, affordable. That affordability is the design's entire
// reason to exist, so it is the default rather than an option.

`ifndef WIREBOUND_GROUPS
`define WIREBOUND_GROUPS 32
`endif

module wirebound #(
    parameter int GROUPS = `WIREBOUND_GROUPS,
    parameter int WIDTH  = 64,
    // Must be a power of two: `^col` over FANIN bits is the balanced tree.
    parameter int FANIN  = 16
) (
    input  logic             clk,
    input  logic             rst,
    input  logic [WIDTH-1:0] din,
    output logic [WIDTH-1:0] dout
);
  // Odd strides, so gcd(STRIDE, GROUPS) == 1 for any power-of-two GROUPS
  // and the fan-in sets walk the whole group space instead of a coset.
  localparam int STRIDE_I = 37;
  localparam int STRIDE_K = 11;

  logic [WIDTH-1:0] r   [GROUPS];
  logic [WIDTH-1:0] nxt [GROUPS];

  for (genvar i = 0; i < GROUPS; i++) begin : g_mix
    logic [FANIN*WIDTH-1:0] terms;

    for (genvar k = 0; k < FANIN; k++) begin : g_term
      localparam int SRC = (i * STRIDE_I + k * STRIDE_K + 1) % GROUPS;
      localparam int ROT = k % WIDTH;
      // A rotation per term, so the WIDTH bits of one source group reach
      // WIDTH different bit positions of the destination and cannot be
      // carried by a single bus.
      assign terms[k*WIDTH+:WIDTH] = (r[SRC] >> ROT) | (r[SRC] << (WIDTH - ROT));
    end

    for (genvar b = 0; b < WIDTH; b++) begin : g_bit
      logic [FANIN-1:0] col;
      for (genvar k = 0; k < FANIN; k++) begin : g_col
        assign col[k] = terms[k*WIDTH+b];
      end
      // Unary reduction, so the frontend emits a balanced tree.
      assign nxt[i][b] = ^col;
    end
  end

  always_ff @(posedge clk) begin
    for (int i = 0; i < GROUPS; i++) begin
      r[i] <= rst ? {WIDTH{1'b0}} : nxt[i];
    end
    // The only primary input, injected at one group: enough to keep the
    // state from being constant-folded away, small enough that IO
    // placement is not part of what is being measured.
    if (!rst) begin
      r[0] <= nxt[0] ^ din;
    end
  end

  assign dout = r[GROUPS-1];
endmodule
