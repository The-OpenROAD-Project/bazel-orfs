// BlockA of test/planned_parent's blocks.sv, the same function in kept
// submodules, one of them in a generate loop: synthesised hierarchically
// and flattened in OpenROAD (OPENROAD_HIERARCHICAL=0), its cell and net
// names carry the hierarchy as `/`, `.`, `[ ]` and yosys's `$`.
module BlockAIn (
    input clock,
    input [119:0] d,
    output reg [119:0] q
);
  always @(posedge clock) q <= d;
endmodule

module BlockALane (
    input clock,
    input [29:0] a,
    input [29:0] b,
    output reg [29:0] q
);
  always @(posedge clock) q <= a ^ b;
endmodule

module BlockACore (
    input clock,
    input [119:0] din_r,
    output [119:0] dout_r
);
  wire [119:0] rot = {din_r[118:0], din_r[119]};
  genvar i;
  generate
    for (i = 0; i < 4; i = i + 1) begin : lane
      BlockALane u_lane (
          .clock(clock),
          .a(rot[30*i+29:30*i]),
          .b(din_r[30*i+29:30*i]),
          .q(dout_r[30*i+29:30*i])
      );
    end
  endgenerate
endmodule

module BlockA (
    input clock,
    input [119:0] din,
    output [119:0] dout
);
  wire [119:0] din_r;
  BlockAIn u_in (
      .clock(clock),
      .d(din),
      .q(din_r)
  );
  BlockACore u_core (
      .clock(clock),
      .din_r(din_r),
      .dout_r(dout)
  );
endmodule
