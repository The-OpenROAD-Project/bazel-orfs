// Toy for sink_registers.py: Src's flush bundle is a mux of registers, one
// of them inside a submodule (RedirectGenerator's role); two Dst consumers
// read it, and Src uses one of the registers itself.
module Gen(
  input  clock,
  input  reset,
  input  a,
  input  en,
  output g
);
  reg g_REG;
  always @(posedge clock or posedge reset) begin
    if (reset)
      g_REG <= 1'h0;
    else
      g_REG <= a ^ en;
  end
  assign g = g_REG;
endmodule

module Src(
  input        clock,
  input        reset,
  input        a,
  input  [3:0] b,
  input        en,
  input        side,
  output       io_flush_valid,
  output [3:0] io_flush_bits,
  output       io_flush_side,
  output       int_use
);
  wire _gen_g;
  reg v;
  reg [3:0] r;
  always @(posedge clock or posedge reset) begin
    if (reset)
      v <= 1'h0;
    else
      v <= a;
  end
  always @(posedge clock) begin
    if (en)
      r <= b;
  end
  Gen gen (
    .clock (clock),
    .reset (reset),
    .a     (a),
    .en    (en),
    .g     (_gen_g)
  );
  assign io_flush_valid = v | _gen_g;
  assign io_flush_bits = v ? r : 4'h0;
  // a leaf: combinational from an input, not a register
  assign io_flush_side = side & v;
  assign int_use = v;
endmodule

// Dst's header declares a group of ports once, as firtool writes them
module Dst(
  input        clock,
  input        reset,
  output [3:0] q,
  input        in_flush_valid,
               in_flush_side,
               x,
  input  [3:0] in_flush_bits
);
  reg [3:0] q_REG;
  always @(posedge clock) begin
    if (in_flush_valid)
      q_REG <= in_flush_bits ^ {4{x ^ in_flush_side}};
  end
  assign q = q_REG;
endmodule

module Top(
  input        clock,
  input        reset,
  input        a,
  input  [3:0] b,
  input        en,
  input        side,
  input        x,
  output [3:0] q1,
  output [3:0] q2,
  output       iu
);
  wire       _src_io_flush_valid;
  wire [3:0] _src_io_flush_bits;
  wire       _src_io_flush_side;
  Src src (
    .clock          (clock),
    .reset          (reset),
    .a              (a),
    .b              (b),
    .en             (en),
    .side           (side),
    .io_flush_valid (_src_io_flush_valid),
    .io_flush_bits  (_src_io_flush_bits),
    .io_flush_side  (_src_io_flush_side),
    .int_use        (iu)
  );
  Dst d1 (
    .clock          (clock),
    .reset          (reset),
    .in_flush_valid (_src_io_flush_valid),
    .in_flush_bits  (_src_io_flush_bits),
    .in_flush_side  (_src_io_flush_side),
    .x              (x),
    .q              (q1)
  );
  Dst d2 (
    .clock          (clock),
    .reset          (reset),
    .in_flush_valid (_src_io_flush_valid),
    .in_flush_bits  (_src_io_flush_bits),
    .in_flush_side  (_src_io_flush_side),
    .x              (~x),
    .q              (q2)
  );
endmodule
