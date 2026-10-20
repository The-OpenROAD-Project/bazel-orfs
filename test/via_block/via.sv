// A parent and a hardened block, with every class of reg2reg path the
// stitched view tells apart (//tools/headroom:classify.tcl):
//   parent:              p0 -> p1, within the parent
//   Pass:                Pass's own q0 -> q
//   Pass->via_top:       Pass's q out to the parent's rq
//   via_top->via:Pass->via_top: the parent's ra, into Pass at a, through
//                        its flop-free logic, out at y, to the parent's rb
module Pass (
    input  logic        clock,
    input  logic [15:0] a,
    input  logic [15:0] d,
    output logic [15:0] y,
    output logic [15:0] q
);
  logic [15:0] q0;
  always_ff @(posedge clock) begin
    q0 <= d;
    q  <= q0 ^ {q0[14:0], q0[15]};
  end
  // in to out, no flop of Pass between
  assign y = (a + 16'h1234) ^ {a[7:0], a[15:8]};
endmodule

module via_top (
    input  logic        clock,
    input  logic [15:0] in,
    output logic [15:0] out
);
  logic [15:0] ra, rb, rq, p0, p1, y, q;
  Pass u_pass (.clock(clock), .a(ra), .d(in), .y(y), .q(q));
  always_ff @(posedge clock) begin
    ra  <= in;
    rb  <= y;
    rq  <= q;
    p0  <= in ^ rb ^ rq;
    p1  <= p0 + 16'h0f0f;
    out <= p1;
  end
endmodule
