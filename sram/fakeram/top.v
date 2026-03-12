module top (
    input [4:0] addr_in,
    input we_in,
    input [7:0] wd_in,
    output [7:0] rd_out,
    input clk,
    input ce_in
  );
  sdq_17x64 u_sdq_17x64 (
    .rd_out(rd_out),
    .addr_in(addr_in),
    .we_in(we_in),
    .wd_in(wd_in),
    .clk(clk),
    .ce_in(ce_in)
  );
endmodule
