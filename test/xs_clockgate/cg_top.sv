// Three register banks, each clocked through its own clock gate: the
// shape of XiangShan's SRAM banks, small enough to synthesise in seconds.
// ClockGate has the ports and the function of XiangShan's Utility
// ClockGate: the enables latched while the clock is low, ANDed with it.
//
// SPDX-License-Identifier: Apache-2.0

module ClockGate (
    input  wire TE,
    input  wire E,
    input  wire CK,
    output wire Q
);
  reg enable_latched;
  always_latch begin
    if (!CK) enable_latched = TE | E;
  end
  assign Q = CK & enable_latched;
endmodule

module bank (
    input  wire       clk,
    input  wire       te,
    input  wire       en,
    input  wire [7:0] d,
    output reg  [7:0] q
);
  wire gclk;
  ClockGate cg (
      .TE(te),
      .E (en),
      .CK(clk),
      .Q (gclk)
  );
  always @(posedge gclk) q <= d;
endmodule

module cg_top (
    input  wire        clk,
    input  wire        te,
    input  wire [ 2:0] en,
    input  wire [ 7:0] d,
    output wire [23:0] q
);
  bank b0 (
      .clk(clk),
      .te (te),
      .en (en[0]),
      .d  (d),
      .q  (q[7:0])
  );
  bank b1 (
      .clk(clk),
      .te (te),
      .en (en[1]),
      .d  (d),
      .q  (q[15:8])
  );
  bank b2 (
      .clk(clk),
      .te (te),
      .en (en[2]),
      .d  (d),
      .q  (q[23:16])
  );
endmodule
