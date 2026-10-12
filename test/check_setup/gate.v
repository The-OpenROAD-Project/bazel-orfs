// An ICG with its enable tied high in front of a flop: the flop is
// clocked through the gate's GCLK.
module top (
    input  clk,
    input  d,
    output q
);
  wire hi, lo, gclk;
  TIEHIx1_ASAP7_75t_R th (.H(hi));
  TIELOx1_ASAP7_75t_R tl (.L(lo));
  ICGx1_ASAP7_75t_R g (
      .CLK (clk),
      .ENA (hi),
      .SE  (lo),
      .GCLK(gclk)
  );
  DFFHQNx1_ASAP7_75t_R r (
      .CLK(gclk),
      .D  (d),
      .QN (q)
  );
endmodule
