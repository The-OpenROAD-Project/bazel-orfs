module accumulator (
    input  logic        clk,
    input  logic [15:0] a,
    output logic [15:0] sum
);
  logic [15:0] a_q;
  always_ff @(posedge clk) begin
    a_q <= a;
    sum <= sum + a_q * a_q[7:0];
  end
endmodule
