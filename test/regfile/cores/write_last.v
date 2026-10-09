// rf_wp.regfile's RTL: when both ports write one word in one cycle, port
// 1, the later, wins.
module rf_wp (
    input        clk,
    input  [2:0] ra,
    output [7:0] rd,
    input  [2:0] wa0,
    input  [7:0] wd0,
    input        we0,
    input  [2:0] wa1,
    input  [7:0] wd1,
    input        we1
);
  reg [7:0] mem[0:7];
  assign rd = mem[ra];
  always @(posedge clk) begin
    if (we0) mem[wa0] <= wd0;
    if (we1) mem[wa1] <= wd1;
  end
endmodule
