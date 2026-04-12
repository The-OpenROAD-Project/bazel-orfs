// Simple counter for testing Docker-based OpenROAD flow.
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
