module ram_64x16(
  input         clk,
                ce_in,
                we_in,
  input  [5:0]  addr_in,
  input  [15:0] wd_in,
  output [15:0] rd_out
);
endmodule

module MemA(
  input        clock,
  input  [7:0] a,
  output [7:0] q
);
  reg  [5:0]  ptr;
  wire [15:0] _ram_rd_out;
  ram_64x16 ram (
    .clk     (clock),
    .ce_in   (1'h1),
    .we_in   (ptr[0]),
    .addr_in (ptr),
    .wd_in   ({a, ~a}),
    .rd_out  (_ram_rd_out)
  );
  always @(posedge clock)
    ptr <= ptr + 6'h1;
  assign q = _ram_rd_out[15:8] ^ _ram_rd_out[7:0];
endmodule

module MemB(
  input        clock,
  input  [7:0] a,
  output [7:0] q
);
  reg  [5:0]  ptr;
  wire [15:0] _ram_rd_out;
  ram_64x16 ram (
    .clk     (clock),
    .ce_in   (1'h1),
    .we_in   (ptr[1]),
    .addr_in (ptr),
    .wd_in   ({~a, a}),
    .rd_out  (_ram_rd_out)
  );
  always @(posedge clock)
    ptr <= ptr - 6'h1;
  assign q = _ram_rd_out[15:8] + _ram_rd_out[7:0];
endmodule

module Plain(
  input        clock,
  input  [7:0] a,
  output [7:0] q
);
  reg  [7:0] r;
  always @(posedge clock)
    r <= r ^ a;
  assign q = r;
endmodule

module MemTop(
  input        clock,
  input  [7:0] a,
  output [7:0] q
);
  wire [7:0] _mema_q;
  wire [7:0] _memb_q;
  wire [7:0] _plain_q;
  MemA mema (
    .clock (clock),
    .a     (a),
    .q     (_mema_q)
  );
  MemB memb (
    .clock (clock),
    .a     (_mema_q),
    .q     (_memb_q)
  );
  Plain plain (
    .clock (clock),
    .a     (a),
    .q     (_plain_q)
  );
  assign q = _memb_q ^ _plain_q;
endmodule
