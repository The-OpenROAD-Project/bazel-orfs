module Lookup(
  input  [3:0] op,
  output reg [3:0] grant,
  output reg [3:0] merge
);
  always @(*) begin
    casez (op)
      4'h0:
        grant = 4'h8;
      4'h1:
        grant = 4'h7;
      4'h2:
        grant = 4'h3;
      4'h3:
        grant = 4'hA;
      4'h4:
        grant = 4'h0;
      4'h5:
        grant = 4'h0;
      4'h6:
        grant = 4'h0;
      4'h7:
        grant = 4'h0;
      4'h8:
        grant = 4'hC;
      4'h9:
        grant = 4'h6;
      4'hA:
        grant = 4'hD;
      4'hB:
        grant = 4'h0;
      4'hC:
        grant = 4'h7;
      4'hD:
        grant = 4'hE;
      4'hE:
        grant = 4'hF;
      4'hF:
        grant = 4'h7;
    endcase
  end
  always @(*) begin
    casez (op)
      4'h0:
        merge = 4'hB;
      4'h1:
        merge = 4'h7;
      4'h2:
        merge = 4'h7;
      4'h3:
        merge = 4'hE;
      4'h4:
        merge = 4'h9;
      4'h5:
        merge = 4'h0;
      4'h6:
        merge = 4'hD;
      4'h7:
        merge = 4'h3;
      4'h8:
        merge = 4'h5;
      4'h9:
        merge = 4'h9;
      4'hA:
        merge = 4'h3;
      4'hB:
        merge = 4'hA;
      4'hC:
        merge = 4'hD;
      4'hD:
        merge = 4'h6;
      4'hE:
        merge = 4'h9;
      4'hF:
        merge = 4'h9;
    endcase
  end
endmodule

module RomTop(
  input        clock,
  input  [3:0] op,
  output reg [3:0] q
);
  wire [3:0] grant, merge;
  reg  [3:0] own;
  Lookup lookup (.op(op), .grant(grant), .merge(merge));
  always @(*) begin
    casez (op)
      4'h0:
        own = 4'hF;
      4'h1:
        own = 4'hC;
      4'h2:
        own = 4'h1;
      4'h3:
        own = 4'hF;
      4'h4:
        own = 4'h7;
      4'h5:
        own = 4'hC;
      4'h6:
        own = 4'hD;
      4'h7:
        own = 4'h5;
      4'h8:
        own = 4'hB;
      4'h9:
        own = 4'hB;
      4'hA:
        own = 4'h2;
      4'hB:
        own = 4'hE;
      4'hC:
        own = 4'h3;
      4'hD:
        own = 4'h5;
      4'hE:
        own = 4'hC;
      4'hF:
        own = 4'hB;
    endcase
  end
  always @(posedge clock)
    q <= grant ^ merge ^ own;
endmodule
