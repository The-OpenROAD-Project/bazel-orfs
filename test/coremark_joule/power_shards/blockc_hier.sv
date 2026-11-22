// BlockC of test/planned_parent's blocks.sv, the same function in two
// kept submodules, hierarchical in OpenROAD: the toy's block cut into
// two simulation shards (u_core replayed on its own, the rest of BlockC
// with it cut out), shard_replays' cuts.
module BlockCIn (
    input clock,
    input [99:0] d,
    output reg [99:0] q
);
  always @(posedge clock) q <= d;
endmodule

module BlockCCore (
    input clock,
    input [99:0] din_r,
    output reg [99:0] dout_r
);
  always @(posedge clock) dout_r <= {din_r[98:0], din_r[99]} ^ din_r;
endmodule

module BlockC (
    input clock,
    input [99:0] din,
    output [99:0] dout
);
  wire [99:0] din_r;
  BlockCIn u_in (
      .clock(clock),
      .d(din),
      .q(din_r)
  );
  BlockCCore u_core (
      .clock(clock),
      .din_r(din_r),
      .dout_r(dout)
  );
endmodule
