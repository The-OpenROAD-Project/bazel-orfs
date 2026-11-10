// Toy for sink_registers.py's hierarchical mode: the register is two levels
// below the parent (P -> Mid m -> Leaf u, like CtrlBlock -> Rob rob ->
// RenameBuffer rab), and the parent's own logic reads the output it drives
// (CtrlBlock's decode buffer reading Rob's canEnq).
module Leaf(
  input        clock,
  input        reset,
  input        go,
  input        stop,
  output       can,
  output [1:0] st_out
);
  reg [1:0] st;
  always @(posedge clock or posedge reset) begin
    if (reset)
      st <= 2'h0;
    else if (go)
      st <= stop ? 2'h0 : st + 2'h1;
  end
  assign can = st == 2'h0;
  assign st_out = st;
endmodule

module Mid(
  input  clock,
  input  reset,
  input  go,
  input  stop,
  input  ok,
  output io_canEnq,
  output io_busy
);
  wire _u_can;
  wire [1:0] _u_st_out;
  Leaf u (
    .clock  (clock),
    .reset  (reset),
    .go     (go),
    .stop   (stop),
    .can    (_u_can),
    .st_out (_u_st_out)
  );
  // a register of Mid itself in the bundle (Rob's allowEnqueue)
  reg allow;
  always @(posedge clock) begin
    allow <= go | stop;
  end
  assign io_canEnq = _u_can & ok & allow;
  assign io_busy = _u_st_out[1];
endmodule

module P(
  input        clock,
  input        reset,
  input        go,
  input        stop,
  input        ok,
  input  [3:0] a,
  output [3:0] q,
  output       busy
);
  wire _m_io_canEnq;
  wire _m_io_busy;
  Mid m (
    .clock     (clock),
    .reset     (reset),
    .go        (go),
    .stop      (stop),
    .ok        (ok),
    .io_canEnq (_m_io_canEnq),
    .io_busy   (_m_io_busy)
  );
  reg [3:0] buf_q;
  always @(posedge clock) begin
    if (_m_io_canEnq)
      buf_q <= a;
  end
  assign q = buf_q;
  assign busy = _m_io_busy;
endmodule
