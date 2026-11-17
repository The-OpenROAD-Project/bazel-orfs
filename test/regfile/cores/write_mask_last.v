// rf_mask.regfile's RTL: each write lands on every word its mask names;
// when both ports write one word in one cycle, port 1, the later, wins.
module rf_mask (
    input        clk,
    input  [2:0] ra,
    output [7:0] rd,
    input  [7:0] wm0,
    input  [7:0] wd0,
    input        we0,
    input  [7:0] wm1,
    input  [7:0] wd1,
    input        we1
);
  reg [7:0] mem[0:7];
  integer k;
  assign rd = mem[ra];
  always @(posedge clk) begin
    for (k = 0; k < 8; k = k + 1) begin
      if (we0 && wm0[k]) mem[k] <= wd0;
      if (we1 && wm1[k]) mem[k] <= wd1;
    end
  end
endmodule
