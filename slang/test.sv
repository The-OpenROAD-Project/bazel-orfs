// Updated SystemVerilog module to test array and struct handling which
// are the features in SystemVerilog that are useful to create nice
// C++ in Verilator and make the Chisel generated code more readable.
//
// test with: verilator --cc test.sv --build --top-module test
module test(
    input logic clk,
    input logic rst_n,
    input logic [7:0] a, b,
    output logic [7:0] sum,
    output logic [1:0] status,
    output logic [3:0] array_out [3:0], // 2D array for testing
    output struct packed {logic [3:0] x, y;} struct_out // Struct for testing
);

  // Register for sum
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

  // Assign values to the array
  always_comb begin
    for (int i = 0; i < 4; i++) begin
      for (int j = 0; j < 4; j++) begin
        array_out[i][j] = logic'(i + j); // Cast to logic (4 bits)
      end
    end
  end

  // Assign values to the struct
  always_comb begin
    struct_out.x = sum[3:0]; // Lower 4 bits of sum
    struct_out.y = sum[7:4]; // Upper 4 bits of sum
  end
endmodule
