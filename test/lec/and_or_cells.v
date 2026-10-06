// y = (a & b) | c in asap7 cells: an AND2 then an OR2.
module and_or_cells(input a, input b, input c, output y);
  wire ab;
  AND2x2_ASAP7_75t_R u_and (.A(a), .B(b), .Y(ab));
  OR2x2_ASAP7_75t_R u_or (.A(ab), .B(c), .Y(y));
endmodule
