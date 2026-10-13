// A 16-entry fully associative TLB: the tags are registers of one
// module, compared with one lookup key; no entry module to count.
module FlatCam(input clock, input [3:0] widx, input wen, input [9:0] wtag,
               input [9:0] key, output hit, output reg [3:0] way);
  reg [9:0] tags [0:15];
  wire [15:0] hits;
  genvar i;
  generate for (i = 0; i < 16; i = i + 1) begin : e
    reg [9:0] tag;
    always @(posedge clock) if (wen && widx == i) tag <= wtag;
    assign hits[i] = tag == key;
  end endgenerate
  assign hit = |hits;
  integer k;
  always @* begin
    way = 0;
    for (k = 15; k >= 0; k = k - 1) if (hits[k]) way = k;
  end
endmodule
