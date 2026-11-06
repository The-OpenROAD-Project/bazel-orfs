// Kept modules nested in each other, for SYNTH_KEEP_MODULES in a
// grouped partition (test/BUILD, nested_kept_synth): nested_inner is
// kept and sits inside nested_outer, which is kept too, so
// nested_outer is not in nested_inner's per-module slice at all.
module nested_inner(
  input        clock,
  input  [7:0] a,
  output [7:0] q
);
  reg [7:0] r;
  always @(posedge clock)
    r <= r + a;
  assign q = r;
endmodule

module nested_outer(
  input        clock,
  input  [7:0] a,
  output [7:0] q
);
  wire [7:0] inner_q;
  reg  [7:0] r;
  nested_inner u_inner(
    .clock(clock),
    .a(a),
    .q(inner_q)
  );
  always @(posedge clock)
    r <= inner_q ^ a;
  assign q = r;
endmodule

module nested_kept_top(
  input        clock,
  input  [7:0] data_in,
  output [7:0] result
);
  wire [7:0] outer_q;
  reg  [7:0] r;
  nested_outer u_outer(
    .clock(clock),
    .a(data_in),
    .q(outer_q)
  );
  always @(posedge clock)
    r <= outer_q + 8'd1;
  assign result = r;
endmodule
