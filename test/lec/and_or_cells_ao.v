// The same function in one cell: AO21 is (A1 & A2) | B.
module and_or_cells(input a, input b, input c, output y);
  AO21x1_ASAP7_75t_R u_ao (.A1(a), .A2(b), .B(c), .Y(y));
endmodule
