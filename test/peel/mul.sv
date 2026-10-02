// The macro of the multiplier example: a pipelined W x W multiplier,
// after test/estimation_ladder/multiplier.sv, with the datapath flops
// left without a reset so ABC can retime them (abc -dff passes only
// $_DFF_ and $_DFFE_ cells). Stage 3 is an empty pipeline stage: the
// product register drives the output port directly, the case peeling
// is for.
module mul #(
    parameter W = 32
) (
    input  logic           clk,
    input  logic           rst,
    input  logic           valid_in,
    input  logic [W-1:0]   a,
    input  logic [W-1:0]   b,
    output logic           valid_out,
    output logic [2*W-1:0] product
);
  logic [W-1:0] a_reg, b_reg;
  logic [2*W-1:0] prod_reg;
  logic v1, v2;
  always_ff @(posedge clk) begin
    a_reg    <= a;
    b_reg    <= b;
    prod_reg <= a_reg * b_reg;
    product  <= prod_reg;
  end
  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      v1        <= 1'b0;
      v2        <= 1'b0;
      valid_out <= 1'b0;
    end else begin
      v1        <= valid_in;
      v2        <= v1;
      valid_out <= v2;
    end
  end
endmodule
