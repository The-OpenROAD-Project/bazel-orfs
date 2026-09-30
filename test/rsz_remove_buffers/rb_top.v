// A broadcast across a kept module: the shape of Frontend's worst nets.
// `en` and `d` are registered at the top and reach N flops in a kept
// submodule and N more at the top, so ABC's `buffer -c` builds chains on
// both sides of the module boundary. `valid_in`, a top-level input port,
// reaches every one of the submodule's N hit flops directly: the net
// repair_design's early sizing round resolves to the top module's
// dbModNet instead of its flat dbNet; each hit flop toggles on it, so
// ABC cannot share it behind one gate. Generate loops, not procedural
// ones: slang unrolls those only to a bounded count.
module rb_unit #(parameter N = 512) (
    input clk,
    input en,
    input valid,
    input [31:0] d,
    input [$clog2(N)-1:0] sel,
    output [31:0] q
);
  localparam W = N / 32;
  wire [31:0] rows [0:W-1];
  wire [N-1:0] hit;
  genvar i;
  generate
    for (i = 0; i < W; i = i + 1) begin : g_row
      reg [31:0] r;
      always @(posedge clk) if (en && sel[$clog2(N)-1:5] == i) r <= d;
      assign rows[i] = r;
    end
    for (i = 0; i < N; i = i + 1) begin : g_hit
      reg h;
      always @(posedge clk) h <= (valid ^ h) | (en & (sel == i));
      assign hit[i] = h;
    end
  endgenerate
  assign q = rows[sel[$clog2(N)-1:5]] ^ {32{^hit}};
endmodule

module rb_top #(parameter N = 512) (
    input clock,
    input en_in,
    input valid_in,
    input [31:0] d_in,
    input [$clog2(N)-1:0] sel_in,
    output [31:0] q,
    output [31:0] r
);
  reg en;
  reg [31:0] d;
  reg [$clog2(N)-1:0] sel;
  wire [N-1:0] top_flops;
  always @(posedge clock) begin
    en <= en_in;
    d <= d_in;
    sel <= sel_in;
  end
  genvar i;
  generate
    for (i = 0; i < N; i = i + 1) begin : g_top
      reg f;
      always @(posedge clock) if (en) f <= d[i % 32] ^ top_flops[(i + 1) % N];
      assign top_flops[i] = f;
    end
  endgenerate
  rb_unit #(.N(N)) u_unit (.clk(clock), .en(en), .valid(valid_in), .d(d), .sel(sel), .q(q));
  assign r = top_flops[31:0] ^ top_flops[N-1:N-32];
endmodule
