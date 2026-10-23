// riscv32i's regfile (flow/designs/src/riscv32i/regfile.v) as the
// alternative to `zero_word 0`: a 31-word register file and x0 in RTL.
// x1..x31 index the array inverted (x31 is word 0, x1 word 30), as
// Rocket indexes its own; x0's index, 31, is no word: writes to x0 are
// dropped and reads of x0 forced to 0 here, outside the array.
module regfile (input         clk,
		input         we3,
		input  [4:0]  ra1, ra2, wa3,
		input  [31:0] wd3,
		output [31:0] rd1, rd2);

   wire [31:0] 		      q1, q2;

   regfile31 rf (.clk(clk),
		 .we3(we3 && wa3 != 0),
		 .ra1(~ra1),
		 .ra2(~ra2),
		 .wa3(~wa3),
		 .wd3(wd3),
		 .rd1(q1),
		 .rd2(q2));

   assign rd1 = (ra1 != 0) ? q1 : 0;
   assign rd2 = (ra2 != 0) ? q2 : 0;

endmodule // regfile

// the array generate_ram builds: 31 words, no zero word
module regfile31 (input         clk,
		  input         we3,
		  input  [4:0]  ra1, ra2, wa3,
		  input  [31:0] wd3,
		  output [31:0] rd1, rd2);

   reg [31:0] 		      rf[30:0];

   always @(posedge clk)
     if (we3) rf[wa3] <= wd3;

   assign rd1 = rf[ra1];
   assign rd2 = rf[ra2];

endmodule // regfile31
