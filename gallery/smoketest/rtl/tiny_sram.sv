// Tiny SRAM-like macro — sub-macro for hierarchical flow testing.
// 8x32 = 256 bits of storage + read/write logic.
module tiny_sram (
    input  wire        clk,
    input  wire        we,
    input  wire  [2:0] addr,
    input  wire [31:0] wdata,
    output reg  [31:0] rdata
);

  reg [31:0] mem [0:7];

  always @(posedge clk) begin
    if (we)
      mem[addr] <= wdata;
    rdata <= mem[addr];
  end

endmodule
