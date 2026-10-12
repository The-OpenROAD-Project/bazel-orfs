// Only the clock's falling edge reaches a rising-edge flop.
module top (
    input  clk,
    input  d,
    output q
);
  wire fclk;
  FALLBUF b (
      .A(clk),
      .Z(fclk)
  );
  DFFHQNx1_ASAP7_75t_R r (
      .CLK(fclk),
      .D  (d),
      .QN (q)
  );
endmodule
