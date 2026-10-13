// const_index.v rewritten as the report recommends: the two pointers
// decoded once in the parent, each entry handed its one-hot bit instead
// of its index. Same function, state and ports as ConstIndex.
module IdxEntryOneHot(input clock, input enq, input deq, input [15:0] in,
                      output [15:0] out);
  reg [15:0] state;
  always @(posedge clock) if (enq) state <= in;
  assign out = deq ? state : 16'h0;
endmodule

module ConstIndex(input clock, input [4:0] enqPtr, input [4:0] deqPtr,
                  input [15:0] in, output [15:0] out);
  wire [31:0] enqOH = 32'b1 << enqPtr;
  wire [31:0] deqOH = 32'b1 << deqPtr;
  wire [15:0] outs [0:31];
  genvar i;
  generate for (i = 0; i < 32; i = i + 1) begin : e
    IdxEntryOneHot entry(.clock(clock), .enq(enqOH[i]), .deq(deqOH[i]),
                         .in(in), .out(outs[i]));
  end endgenerate
  reg [15:0] acc;
  integer k;
  always @* begin
    acc = 0;
    for (k = 0; k < 32; k = k + 1) acc = acc | outs[k];
  end
  assign out = acc;
endmodule
