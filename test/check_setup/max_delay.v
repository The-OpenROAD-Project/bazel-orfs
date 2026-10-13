// Two registers between the ports: the SDC budgets d -> r -> q with
// set_max_delay and leaves e -> u -> p without any constraint.
module top (
    input  clk,
    input  d,
    input  e,
    output q,
    output p
);
  DFFHQNx1_ASAP7_75t_R r (
      .CLK(clk),
      .D  (d),
      .QN (q)
  );
  DFFHQNx1_ASAP7_75t_R u (
      .CLK(clk),
      .D  (e),
      .QN (p)
  );
endmodule
