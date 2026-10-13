// A 16 x 8 register file with two read and one write port: a memory,
// which the register-file generator owns; none of the detectors' shapes.
module Rf2r1w(input clock, input [3:0] ra0, input [3:0] ra1, input [3:0] wa,
              input [7:0] wd, input we, output [7:0] rd0, output [7:0] rd1);
  reg [7:0] mem [0:15];
  always @(posedge clock) if (we) mem[wa] <= wd;
  assign rd0 = mem[ra0];
  assign rd1 = mem[ra1];
endmodule
