module ALU(
    input clk,
    input [31:0] a,
    input [31:0] b,
    input [2:0] op,
    output reg [31:0] out
    );
    reg [31:0] aReg;
    reg [31:0] bReg;
    reg [2:0] opReg;

    always @*
    begin
        case(opReg)
            3'b001: out = aReg + bReg;
            3'b010: out = aReg & bReg;
            3'b011: out = aReg | bReg;
            default: out = 32'd0;       // Handle other cases or add a default value
        endcase
    end
    always @(posedge clk) begin
        aReg <= a;
        bReg <= b;
        opReg <= op;
    end
endmodule
