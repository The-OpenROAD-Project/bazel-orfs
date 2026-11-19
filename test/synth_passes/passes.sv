module Adder (
    input  logic        clock,
    input  logic [15:0] a,
    input  logic [15:0] b,
    output logic [15:0] y
);
  always_ff @(posedge clock) y <= a + b;
endmodule

module Mult (
    input  logic        clock,
    input  logic [7:0]  a,
    input  logic [7:0]  b,
    output logic [15:0] y
);
  always_ff @(posedge clock) y <= a * b;
endmodule

module PassesTop (
    input  logic        clock,
    input  logic [15:0] a,
    input  logic [15:0] b,
    output logic [15:0] y
);
  logic [15:0] sum, product;
  Adder adder (.clock, .a, .b, .y(sum));
  Mult mult (.clock, .a(a[7:0]), .b(b[7:0]), .y(product));
  always_ff @(posedge clock) y <= sum ^ product;
endmodule
