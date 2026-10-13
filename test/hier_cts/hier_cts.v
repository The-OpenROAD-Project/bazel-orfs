// Registers in the top module and in a kept submodule, on one clock and
// side by side, so CTS hangs both from the same leaf buffers.
module hc_bank (
    input             clk,
    input      [63:0] d,
    output reg [63:0] q
);
  always @(posedge clk) q <= d;
endmodule

module hier_cts (
    input         clk,
    input  [63:0] d,
    output [63:0] q
);
  reg  [63:0] r;
  reg  [63:0] s;
  wire [63:0] m;
  always @(posedge clk) r <= d;
  hc_bank u_bank (
      .clk(clk),
      .d  (r),
      .q  (m)
  );
  always @(posedge clk) s <= m ^ r;
  assign q = s;
endmodule
