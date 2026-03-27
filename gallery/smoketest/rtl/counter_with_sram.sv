// Hierarchical top — counter with SRAM sub-macro.
// Exercises the macro abstract flow: tiny_sram is built separately,
// then integrated via LEF/LIB abstracts.
module counter_with_sram (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    input  wire        we,
    input  wire  [2:0] addr,
    input  wire [31:0] wdata,
    output wire [31:0] count,
    output wire [31:0] rdata
);

  counter u_counter (
      .clk    (clk),
      .rst    (rst),
      .enable (enable),
      .count  (count)
  );

  tiny_sram u_sram (
      .clk   (clk),
      .we    (we),
      .addr  (addr),
      .wdata (wdata),
      .rdata (rdata)
  );

endmodule
