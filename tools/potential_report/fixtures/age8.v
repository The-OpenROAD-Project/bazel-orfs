// An 8-entry age matrix: age_i_j says entry i is older than entry j,
// the shape of XiangShan's AgeDetector.
module Age8(input clock, input [7:0] enq, input [7:0] valid,
            output [7:0] oldest);
  wire [63:0] agew;
  genvar i, j;
  generate for (i = 0; i < 8; i = i + 1) begin : r
    wire [7:0] older;
    for (j = 0; j < 8; j = j + 1) begin : c
      if (i == j) begin : d
        assign older[j] = 1'b1;
      end else if (i < j) begin : u
        reg age;
        always @(posedge clock) if (enq[i] | enq[j]) age <= enq[j];
        assign agew[i * 8 + j] = age;
        assign older[j] = age | ~valid[j];
      end else begin : l
        assign older[j] = ~agew[j * 8 + i] | ~valid[j];
      end
    end
    assign oldest[i] = valid[i] & (&older);
  end endgenerate
endmodule
