// A unit with a kept module, PunCore, whose netlist (punched_netlist.v)
// has the ports a hierarchical global route punches: the two-level
// replay's toy (flow/power.bzl's shard_replays two_level).
module PunIn (
    input clock,
    input [3:0] d,
    output reg [3:0] q
);
  always @(posedge clock) q <= d;
endmodule

// q feeds itself: in the netlist one such load reads q[0] back through
// the parent's buffers. mode is only ever written one constant, 2'b10,
// and never in the toy's run (en is 0): the RTL holds its start value,
// 0, while synthesis folds it to the constant it can only ever take,
// tie cells in the netlist, and `en`, which only enabled that write, is
// no port of the netlist. tag is never used: the parent's netlist leaves
// the net at its pin [1] undriven. acc takes data when v is set: data is
// a don't-care while v is 0. rdy is 1 out of reset, registered: as
// XiangShan's ready outputs, its value before the first reset is the
// simulator's, not the design's.
module PunCore (
    input clock,
    input reset,
    input en,
    input [3:0] d,
    input [1:0] tag,
    input v,
    input [1:0] data,
    output reg [3:0] q,
    output reg [1:0] mode,
    output reg [1:0] acc,
    output reg rdy
);
  always @(posedge clock) q <= {q[2:0], q[3]} ^ d;
  always @(posedge clock) if (en) mode <= 2'b10;
  always @(posedge clock) if (v) acc <= data;
  always @(posedge clock) rdy <= !reset;
endmodule

module Punched (
    input clock,
    input reset,
    input [3:0] din,
    output [3:0] dout
);
  wire [3:0] r;
  PunIn u_in (
      .clock(clock),
      .d(din),
      .q(r)
  );
  PunCore u_core (
      .clock(clock),
      .reset(reset),
      .en(1'b0),
      .d(r),
      .tag(r[1:0]),
      .v(r[3]),
      .data(r[1:0]),
      .q(dout),
      .mode(),
      .acc(),
      .rdy()
  );
endmodule
