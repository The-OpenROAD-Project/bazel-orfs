// A 16-entry CAM: every entry holds a tag and compares it with one
// broadcast key; the hits are reduced to a match and its index.
module CamEntry(input clock, input wen, input [7:0] wdata, input [7:0] key,
                output hit);
  reg [7:0] tag;
  always @(posedge clock) if (wen) tag <= wdata;
  assign hit = tag == key;
endmodule

module Cam16(input clock, input [15:0] wen, input [7:0] wdata,
             input [7:0] key, output match, output reg [3:0] index);
  wire [15:0] hits;
  genvar i;
  generate for (i = 0; i < 16; i = i + 1) begin : e
    CamEntry entry(.clock(clock), .wen(wen[i]), .wdata(wdata), .key(key),
                   .hit(hits[i]));
  end endgenerate
  assign match = |hits;
  integer k;
  always @* begin
    index = 0;
    for (k = 15; k >= 0; k = k - 1) if (hits[k]) index = k;
  end
endmodule
