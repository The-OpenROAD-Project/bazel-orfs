// Minimal multi-module design for testing SYNTH_KEEP_MODULES.
// Three modules: two sub-modules (adder, counter) and a top.
module adder(
  input  [7:0] a,
  input  [7:0] b,
  output [8:0] sum
);
  assign sum = a + b;
endmodule

module counter(
  input        clk,
  input        reset,
  output [7:0] count
);
  reg [7:0] cnt;
  always @(posedge clk or posedge reset)
    if (reset)
      cnt <= 8'd0;
    else
      cnt <= cnt + 8'd1;
  assign count = cnt;
endmodule

module kept_modules_top(
  input        clk,
  input        reset,
  input  [7:0] data_in,
  output [8:0] result
);
  wire [7:0] count;
  counter u_counter(
    .clk(clk),
    .reset(reset),
    .count(count)
  );
  adder u_adder(
    .a(count),
    .b(data_in),
    .sum(result)
  );
endmodule
