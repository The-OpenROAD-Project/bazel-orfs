// Tiny counter — simplest possible design for mock flow testing.
// ~50 cells: 32 flip-flops + incrementer + output mux.
module counter (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    output wire [31:0] count
);

  reg [31:0] counter_reg;

  always @(posedge clk) begin
    if (rst)
      counter_reg <= 32'd0;
    else if (enable)
      counter_reg <= counter_reg + 32'd1;
  end

  assign count = counter_reg;

endmodule
