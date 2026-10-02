// The parent: Src's registered output crosses the die into Dst.
module top #(
    parameter W = 32
) (
    input  logic         clock,
    input  logic [W-1:0] din,
    output logic [W-1:0] dout
);
  logic [W-1:0] x;
  Src u_src (
      .clock(clock),
      .din  (din),
      .dout (x)
  );
  Dst u_dst (
      .clock(clock),
      .din  (x),
      .dout (dout)
  );
endmodule
