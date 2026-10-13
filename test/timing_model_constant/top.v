// A register on each of the block's outputs.
module top (
    input clk,
    input d
);
  wire q, z0, z1, zand;
  blk u (
      .clk (clk),
      .d   (d),
      .q   (q),
      .z0  (z0),
      .z1  (z1),
      .zand(zand)
  );
  DFFHQNx1_ASAP7_75t_R rq (
      .CLK(clk),
      .D  (q)
  );
  DFFHQNx1_ASAP7_75t_R r0 (
      .CLK(clk),
      .D  (z0)
  );
  DFFHQNx1_ASAP7_75t_R r1 (
      .CLK(clk),
      .D  (z1)
  );
  DFFHQNx1_ASAP7_75t_R rz (
      .CLK(clk),
      .D  (zand)
  );
endmodule
