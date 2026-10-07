// riscv32i's register file and the netlist generate_regfile writes for
// it, on the same inputs, both reads of each side out.
module tb_top (
    input         clk,
    input         we3,
    input  [4:0]  ra1,
    input  [4:0]  ra2,
    input  [4:0]  wa3,
    input  [31:0] wd3,
    output [31:0] rd1_rtl,
    output [31:0] rd2_rtl,
    output [31:0] rd1_gen,
    output [31:0] rd2_gen
);
  regfile rtl (
      .clk(clk), .we3(we3), .ra1(ra1), .ra2(ra2), .wa3(wa3), .wd3(wd3),
      .rd1(rd1_rtl), .rd2(rd2_rtl)
  );
  regfile_gen gen (
      .clk(clk), .we3(we3), .ra1(ra1), .ra2(ra2), .wa3(wa3), .wd3(wd3),
      .rd1(rd1_gen), .rd2(rd2_gen)
  );
endmodule
