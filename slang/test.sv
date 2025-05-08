// simple system verilog module, adds two numbers, uses a clock,
// reset, register and a smoke-test SystemVerilog language feature
module test(input logic clk, input logic rst_n, input logic [7:0] a, b,
            output logic [7:0] sum, output logic [1:0] status);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      sum <= 8'b0;
    else
      sum <= a + b;
  end

  // SystemVerilog-only synthesizable feature: unique case
  always_comb begin
    unique case (sum)
      8'b0: status = 2'b00;       // Sum is zero
      8'b11111111: status = 2'b01; // Sum is max value
      default: status = 2'b10;    // Other values
    endcase
  end
endmodule
