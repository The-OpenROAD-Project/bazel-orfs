// A block with a register-driven output and three constant ones: tied
// low, tied high, and an AND of a register with a tie-low cell, a
// constant only constant propagation finds.
module blk (
    input  clk,
    input  d,
    output q,
    output z0,
    output z1,
    output zand
);
  wire qn, lo, hi;
  DFFHQNx1_ASAP7_75t_R r (
      .CLK(clk),
      .D  (d),
      .QN (qn)
  );
  BUFx2_ASAP7_75t_R bq (
      .A(qn),
      .Y(q)
  );
  TIELOx1_ASAP7_75t_R tl (.L(lo));
  TIEHIx1_ASAP7_75t_R th (.H(hi));
  BUFx2_ASAP7_75t_R b0 (
      .A(lo),
      .Y(z0)
  );
  BUFx2_ASAP7_75t_R b1 (
      .A(hi),
      .Y(z1)
  );
  AND2x2_ASAP7_75t_R a (
      .A(qn),
      .B(lo),
      .Y(zand)
  );
endmodule
