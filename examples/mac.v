// Multiply-accumulate: acc <= acc + a * b on every enabled clock.
//
// Small enough to run the whole ORFS flow on asap7 in a couple of minutes,
// large enough to have a real timing path (the multiplier feeding the
// adder) for the GUI to show.
module mac (
    input             clk,
    input             rst,
    input             en,
    input      [7:0]  a,
    input      [7:0]  b,
    output reg [23:0] acc
);

  always @(posedge clk) begin
    if (rst) begin
      acc <= 24'd0;
    end else if (en) begin
      acc <= acc + a * b;
    end
  end

endmodule
