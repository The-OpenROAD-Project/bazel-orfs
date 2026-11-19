// Top keeps Mid (which keeps Leaf) and Other. Registers in every module,
// paths within each and across every boundary, and combinational paths
// through Leaf and Other, so a timing model sits on some shard's paths.
module Leaf (
    input clock,
    input [7:0] d,
    output [7:0] q
);
  reg [7:0] r;
  always @(posedge clock) r <= d * 8'd3 + 8'd1;
  assign q = r ^ d;
endmodule

module Mid (
    input clock,
    input [7:0] d,
    output [7:0] q
);
  reg [7:0] r;
  wire [7:0] lq;
  Leaf leaf (
      .clock(clock),
      .d(r),
      .q(lq)
  );
  always @(posedge clock) r <= d + lq;
  assign q = r;
endmodule

module Other (
    input clock,
    input [7:0] d,
    output [7:0] q
);
  reg [7:0] r;
  always @(posedge clock) r <= d * d;
  assign q = r + d;
endmodule

module Top (
    input clock,
    input [7:0] in,
    output [7:0] out
);
  reg [7:0] a, b;
  wire [7:0] mq, oq;
  Mid mid (
      .clock(clock),
      .d(a),
      .q(mq)
  );
  Other other (
      .clock(clock),
      .d(mq ^ b),
      .q(oq)
  );
  always @(posedge clock) begin
    a <= in + oq;
    b <= oq;
  end
  assign out = b;
endmodule
