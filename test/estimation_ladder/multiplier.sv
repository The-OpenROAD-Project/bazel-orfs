// Generic parameterizable pipelined multiplier for estimation ladder testing.
// Zero-leakage, standard SystemVerilog implementation.

module multiplier #(
    parameter int WIDTH = 32
) (
    input  logic                 clk,
    input  logic                 rst,
    input  logic                 valid_in,
    input  logic [WIDTH-1:0]     a,
    input  logic [WIDTH-1:0]     b,
    output logic                 valid_out,
    output logic [2*WIDTH-1:0]   product
);

    // Stage 1: Register inputs
    logic [WIDTH-1:0] a_reg, b_reg;
    logic             v1_reg;

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            a_reg   <= '0;
            b_reg   <= '0;
            v1_reg  <= 1'b0;
        end else begin
            a_reg   <= a;
            b_reg   <= b;
            v1_reg  <= valid_in;
        end
    end

    // Stage 2: Multiply
    logic [2*WIDTH-1:0] prod_reg;
    logic               v2_reg;

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            prod_reg <= '0;
            v2_reg   <= 1'b0;
        end else begin
            prod_reg <= a_reg * b_reg;
            v2_reg   <= v1_reg;
        end
    end

    // Stage 3: Output register
    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            product   <= '0;
            valid_out <= 1'b0;
        end else begin
            product   <= prod_reg;
            valid_out <= v2_reg;
        end
    end

endmodule
