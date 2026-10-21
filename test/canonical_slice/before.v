module other(input clk, input [1:0] sel, input [7:0] a, output reg [7:0] y);
  always @(posedge clk)
    case (sel)
      2'd0: y <= a;
      default: y <= ~a;
    endcase
endmodule

module unit(input clk, input [1:0] sel, input [7:0] a, b, output reg [7:0] y);
  always @(posedge clk)
    case (sel)
      2'd0: y <= a + b;
      2'd1: y <= a - b;
      2'd2: y <= a & b;
      default: y <= a ^ b;
    endcase
endmodule

module top(input clk, input [1:0] sel, input [7:0] a, b, output [7:0] y, z);
  other o(.clk(clk), .sel(sel), .a(a), .y(z));
  unit u(.clk(clk), .sel(sel), .a(a), .b(b), .y(y));
endmodule
