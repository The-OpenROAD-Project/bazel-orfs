// A reorder-buffer-shaped array at XiangShan's scale: 256 entries that
// each compare their own index with two enqueue and two dequeue
// pointers (RobEntryCell's shape), against the same array with the
// pointers decoded once in the parent (the rewrite the potential report
// recommends). Same state, same function, same ports.
module RobLikeEntry(input clock, input [7:0] idx,
                    input [7:0] enq0, input [7:0] enq1,
                    input [7:0] deq0, input [7:0] deq1,
                    input [31:0] in0, input [31:0] in1,
                    output [31:0] out0, output [31:0] out1);
  reg [31:0] state;
  always @(posedge clock)
    if (idx == enq1) state <= in1;
    else if (idx == enq0) state <= in0;
  assign out0 = (idx == deq0) ? state : 32'h0;
  assign out1 = (idx == deq1) ? state : 32'h0;
endmodule

module RobLikeEntryOneHot(input clock, input enq0, input enq1,
                          input deq0, input deq1,
                          input [31:0] in0, input [31:0] in1,
                          output [31:0] out0, output [31:0] out1);
  reg [31:0] state;
  always @(posedge clock)
    if (enq1) state <= in1;
    else if (enq0) state <= in0;
  assign out0 = deq0 ? state : 32'h0;
  assign out1 = deq1 ? state : 32'h0;
endmodule

module RobLike #(parameter ONEHOT = 0)
  (input clock, input [7:0] enq0, input [7:0] enq1, input [7:0] deq0,
   input [7:0] deq1, input [31:0] in0, input [31:0] in1,
   output reg [31:0] out0, output reg [31:0] out1);
  // Registered pointers and ports: every path is register to register.
  reg [7:0] e0, e1, d0, d1;
  reg [31:0] i0, i1;
  always @(posedge clock) begin
    e0 <= enq0; e1 <= enq1; d0 <= deq0; d1 <= deq1; i0 <= in0; i1 <= in1;
  end
  wire [255:0] e0h = 256'b1 << e0, e1h = 256'b1 << e1;
  wire [255:0] d0h = 256'b1 << d0, d1h = 256'b1 << d1;
  wire [31:0] o0 [0:255];
  wire [31:0] o1 [0:255];
  genvar i;
  generate for (i = 0; i < 256; i = i + 1) begin : e
    if (ONEHOT) begin : h
      RobLikeEntryOneHot entry(.clock(clock), .enq0(e0h[i]), .enq1(e1h[i]),
        .deq0(d0h[i]), .deq1(d1h[i]), .in0(i0), .in1(i1),
        .out0(o0[i]), .out1(o1[i]));
    end else begin : c
      RobLikeEntry entry(.clock(clock), .idx(i[7:0]), .enq0(e0), .enq1(e1),
        .deq0(d0), .deq1(d1), .in0(i0), .in1(i1),
        .out0(o0[i]), .out1(o1[i]));
    end
  end endgenerate
  reg [31:0] a0, a1;
  integer k;
  always @* begin
    a0 = 0; a1 = 0;
    for (k = 0; k < 256; k = k + 1) begin a0 = a0 | o0[k]; a1 = a1 | o1[k]; end
  end
  always @(posedge clock) begin out0 <= a0; out1 <= a1; end
endmodule
