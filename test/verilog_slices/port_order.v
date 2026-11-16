module array_64x16(
  input  [5:0]  RW0_addr,
  input         RW0_en,
                RW0_clk,
                RW0_wmode,
  input  [15:0] RW0_wdata,
  output [15:0] RW0_rdata,
  input  [1:0]  RW0_wmask
);
  reg [15:0] Memory[0:63];
  reg [5:0]  _RW0_raddr_d0;
  reg        _RW0_ren_d0;
  reg        _RW0_rmode_d0;
  always @(posedge RW0_clk) begin
    _RW0_raddr_d0 <= RW0_addr;
    _RW0_ren_d0 <= RW0_en;
    _RW0_rmode_d0 <= RW0_wmode;
    if (RW0_en & RW0_wmask[0] & RW0_wmode)
      Memory[RW0_addr][32'h0 +: 8] <= RW0_wdata[7:0];
    if (RW0_en & RW0_wmask[1] & RW0_wmode)
      Memory[RW0_addr][32'h8 +: 8] <= RW0_wdata[15:8];
  end
  assign RW0_rdata = _RW0_ren_d0 & ~_RW0_rmode_d0 ? Memory[_RW0_raddr_d0] : 16'bx;
endmodule

module Bank(
  input         RW0_clk,
  input  [5:0]  RW0_addr,
  input         RW0_en,
                RW0_wmode,
  input  [1:0]  RW0_wmask,
  input  [15:0] RW0_wdata,
  output [15:0] RW0_rdata
);
  array_64x16 array_ext (
    .RW0_addr  (RW0_addr),
    .RW0_en    (RW0_en),
    .RW0_clk   (RW0_clk),
    .RW0_wmode (RW0_wmode),
    .RW0_wdata (RW0_wdata),
    .RW0_rdata (RW0_rdata),
    .RW0_wmask (RW0_wmask)
  );
endmodule

module PortOrderTop(
  input         clock,
  input  [15:0] RW0_wdata,
  output [15:0] RW0_rdata,
  input  [1:0]  RW0_wmask,
  input         RW0_wmode,
  input         RW0_en,
  input  [5:0]  RW0_addr
);
  Bank bank (
    .RW0_clk   (clock),
    .RW0_addr  (RW0_addr),
    .RW0_en    (RW0_en),
    .RW0_wmode (RW0_wmode),
    .RW0_wmask (RW0_wmask),
    .RW0_wdata (RW0_wdata),
    .RW0_rdata (RW0_rdata)
  );
endmodule
