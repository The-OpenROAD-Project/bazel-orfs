// SystemVerilog counter exercising features that require the slang frontend.
//
// Features used (all rejected by yosys built-in Verilog frontend):
//   - typedef enum
//   - always_ff / always_comb
//   - logic (as net type)
//   - unique case
//   - automatic function with return
//   - package import (counter_pkg::*)

package counter_pkg;
  typedef enum logic [1:0] {
    IDLE  = 2'b00,
    COUNT = 2'b01,
    HOLD  = 2'b10
  } mode_t;

  parameter int STEP = 1;
endpackage

module counter
  import counter_pkg::*;
(
    input  logic        clk,
    input  logic        rst,
    input  logic        enable,
    input  logic [1:0]  mode_sel,
    output logic [31:0] count
);

  logic [31:0] counter_reg;
  mode_t       mode;

  // Decode mode from raw select bits
  always_comb begin
    unique case (mode_sel)
      2'b00:   mode = IDLE;
      2'b01:   mode = COUNT;
      default: mode = HOLD;
    endcase
  end

  // Automatic function — valid SystemVerilog, but yosys built-in
  // frontend cannot parse the `automatic` keyword.
  function automatic logic [31:0] next_count(
    input logic [31:0] current,
    input mode_t       m
  );
    unique case (m)
      IDLE:    return 32'd0;
      COUNT:   return current + STEP;
      default: return current;
    endcase
  endfunction

  always_ff @(posedge clk) begin
    if (rst)
      counter_reg <= 32'd0;
    else if (enable)
      counter_reg <= next_count(counter_reg, mode);
  end

  assign count = counter_reg;

endmodule
