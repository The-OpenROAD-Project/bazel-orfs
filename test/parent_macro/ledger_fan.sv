// The crossing ledger's feed-throughs (tools/carve/crossing_ledger.tcl)
// on a part of their own: y has every a behind it, more inputs than the
// ledger's first pass lists into it (LEDGER_ARCS_K 2); w has b and c,
// which ledger_fan.sdc puts in different budget groups, as it does a[1]
// and a[3] from a[0] and a[2]; a[0] and c each feed two outputs. The
// register gives the part its clock.
module ledger_fan (
    input  logic       clock,
    input  logic [3:0] a,
    input  logic       b,
    input  logic       c,
    input  logic       d,
    output logic       y,
    output logic       w,
    output logic       x,
    output logic       q
);
  assign y = ^a;
  assign w = b & c;
  assign x = a[0] | c;
  always_ff @(posedge clock) q <= d;
endmodule
