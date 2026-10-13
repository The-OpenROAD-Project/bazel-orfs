// 32 entries that each compare their own constant index with two
// shared pointers, the way XiangShan's RobEntryCell does: 64 five-bit
// compares that are two shared 5->32 decoders in disguise.
module IdxEntry(input clock, input [4:0] idx, input [4:0] enqPtr,
                input [4:0] deqPtr, input [15:0] in, output [15:0] out);
  reg [15:0] state;
  always @(posedge clock) if (idx == enqPtr) state <= in;
  assign out = (idx == deqPtr) ? state : 16'h0;
endmodule

module ConstIndex(input clock, input [4:0] enqPtr, input [4:0] deqPtr,
                  input [15:0] in, output [15:0] out);
  wire [15:0] outs [0:31];
  genvar i;
  generate for (i = 0; i < 32; i = i + 1) begin : e
    IdxEntry entry(.clock(clock), .idx(i[4:0]), .enqPtr(enqPtr),
                   .deqPtr(deqPtr), .in(in), .out(outs[i]));
  end endgenerate
  reg [15:0] acc;
  integer k;
  always @* begin
    acc = 0;
    for (k = 0; k < 32; k = k + 1) acc = acc | outs[k];
  end
  assign out = acc;
endmodule
