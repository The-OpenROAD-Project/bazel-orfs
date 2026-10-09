// The negative control for rf_wp.regfile: port 0, the earlier, wins a
// collision. Against `write_priority last` some read must differ, or the
// stimulus never collides.
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
    if (we1) mem[wa1] <= wd1;
    if (we0) mem[wa0] <= wd0;
  end
endmodule
