// Top instantiates Block twice; Block is a macro of Top, hardened by its
// own flow, and keeps Inner so its synthesis is partitioned.
module Inner (
    input clock,
    input [3:0] d,
    output [3:0] q
);
  reg [3:0] r;
  always @(posedge clock) r <= d + 4'd1;
  assign q = r;
endmodule

module Block (
    input clock,
    input [3:0] in_bits,
    input in_valid,
    output [3:0] out_bits,
    output out_valid
);
  reg [3:0] r;
  reg v;
  wire [3:0] q;
  Inner inner (
      .clock(clock),
      .d(r),
      .q(q)
  );
  always @(posedge clock) begin
    r <= in_bits ^ q;
    v <= in_valid;
  end
  assign out_bits = q ^ in_bits;
  assign out_valid = v;
endmodule

module Top (
    input clock,
    input [3:0] a,
    input a_valid,
    output [3:0] z,
    output z_valid
);
  wire [3:0] mid;
  wire mid_valid;
  reg [3:0] r;
  reg rv;
  Block first (
      .clock(clock),
      .in_bits(a),
      .in_valid(a_valid),
      .out_bits(mid),
      .out_valid(mid_valid)
  );
  always @(posedge clock) begin
    r <= mid + 4'd3;
    rv <= mid_valid;
  end
  Block second (
      .clock(clock),
      .in_bits(r),
      .in_valid(rv),
      .out_bits(z),
      .out_valid(z_valid)
  );
endmodule
