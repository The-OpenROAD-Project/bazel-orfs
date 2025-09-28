module Formal (
      input clock,
      input reset,
      input [3:0] cnt,
      output [3:0] fv
    );
    assign fv = cnt;
    `ifdef FORMAL
      initial assume(reset==1'b1);
      initial assume(cnt==4'b0);

      always @(posedge clock) begin
        assert(cnt <= 10);
      end
    `endif
endmodule
