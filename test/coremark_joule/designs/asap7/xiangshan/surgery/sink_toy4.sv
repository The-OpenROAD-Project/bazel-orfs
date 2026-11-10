// Toy for sink_registers.py at depth: the registers two levels below the
// source, in a module instanced twice (MemBlock -> NewLoadUnit x3 -> s2
// stage), the bundle read by a sibling of the source.
module Stage(
  input  clock,
  input  reset,
  input  in_valid,
  output out_valid
);
  reg pipeOutValid;
  always @(posedge clock or posedge reset) begin
    if (reset)
      pipeOutValid <= 1'h0;
    else
      pipeOutValid <= in_valid;
  end
  assign out_valid = pipeOutValid;
endmodule

module Unit(
  input  clock,
  input  reset,
  input  in_valid,
  output io_valid
);
  Stage s (
    .clock     (clock),
    .reset     (reset),
    .in_valid  (in_valid),
    .out_valid (io_valid)
  );
endmodule

module Src(
  input  clock,
  input  reset,
  input  a,
  input  b,
  output io_wake_0,
  output io_wake_1,
  output io_any
);
  wire _u0_io_valid;
  wire _u1_io_valid;
  Unit u0 (
    .clock    (clock),
    .reset    (reset),
    .in_valid (a),
    .io_valid (_u0_io_valid)
  );
  Unit u1 (
    .clock    (clock),
    .reset    (reset),
    .in_valid (b),
    .io_valid (_u1_io_valid)
  );
  assign io_wake_0 = _u0_io_valid;
  assign io_wake_1 = _u1_io_valid;
  assign io_any = _u0_io_valid | _u1_io_valid;
endmodule

module Dst(
  input        clock,
  input        w0,
  input        w1,
  input        any,
  output [1:0] q
);
  reg [1:0] q_REG;
  always @(posedge clock) begin
    if (any)
      q_REG <= {w1, w0};
  end
  assign q = q_REG;
endmodule

module Top(
  input        clock,
  input        reset,
  input        a,
  input        b,
  output [1:0] q
);
  wire _src_io_wake_0;
  wire _src_io_wake_1;
  wire _src_io_any;
  Src src (
    .clock     (clock),
    .reset     (reset),
    .a         (a),
    .b         (b),
    .io_wake_0 (_src_io_wake_0),
    .io_wake_1 (_src_io_wake_1),
    .io_any    (_src_io_any)
  );
  Dst d (
    .clock (clock),
    .w0    (_src_io_wake_0),
    .w1    (_src_io_wake_1),
    .any   (_src_io_any),
    .q     (q)
  );
endmodule
