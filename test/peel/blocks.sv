// Two hardened blocks far apart on the parent's die. Src's output is
// registered right at its port, a flop the parent cannot place: it sits
// inside Src, so the whole crossing to Dst is one stage after it. Peeled
// (see BUILD.bazel), the flop moves to a wrapper the parent flattens and
// its placer can put it anywhere along the crossing.
module Src #(
    parameter W = 32
) (
    input  logic         clock,
    input  logic [W-1:0] din,
    output logic [W-1:0] dout
);
  logic [W-1:0] r_in;
  logic [W-1:0] r_out;
  always_ff @(posedge clock) begin
    r_in  <= din;
    r_out <= r_in ^ {r_in[0], r_in[W-1:1]};
  end
  assign dout = r_out;
endmodule

module Dst #(
    parameter W = 32
) (
    input  logic         clock,
    input  logic [W-1:0] din,
    output logic [W-1:0] dout
);
  logic [W-1:0] r;
  always_ff @(posedge clock) r <= din ^ {din[0], din[W-1:1]};
  assign dout = r;
endmodule
