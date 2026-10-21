// A cone cut by a kept module: r1 -> logic in the top -> logic in kc_mid
// (kept) -> logic in the top -> r2. The census must see the path cross
// kc_mid's boundary twice between logic cells. A second path, r1 -> kc_reg
// (kept, registered at its input), crosses only at a register: no row.
module kc_mid (
    input  [7:0] a,
    output [7:0] y
);
  assign y = (a ^ {a[6:0], a[7]}) & {a[0], a[7:1]};
endmodule

module kc_reg (
    input            clk,
    input      [7:0] a,
    output reg [7:0] q
);
  always @(posedge clk) q <= a;
endmodule

module keep_census (
    input            clk,
    input      [7:0] in,
    output reg [7:0] out,
    output     [7:0] out2
);
  reg  [7:0] r1;
  wire [7:0] m;
  kc_mid mid (
      .a(r1 + 8'd3),
      .y(m)
  );
  kc_reg rg (
      .clk(clk),
      .a  (r1),
      .q  (out2)
  );
  always @(posedge clk) begin
    r1  <= in;
    out <= (m | r1) ^ {m[3:0], m[7:4]};
  end
endmodule
