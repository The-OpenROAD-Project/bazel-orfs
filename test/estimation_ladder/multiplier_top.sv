module multiplier_top #(
    parameter int WIDTH = 128,
    parameter int MACRO_WIDTH = 32
) (
    input  logic                 clk,
    input  logic                 rst,
    input  logic                 valid_in,
    input  logic [WIDTH-1:0]     a,
    input  logic [WIDTH-1:0]     b,
    output logic                 valid_out,
    output logic [2*WIDTH-1:0]   product
);
    localparam NUM_MACROS = WIDTH / MACRO_WIDTH;
    
    logic [2*MACRO_WIDTH-1:0] partial_products [NUM_MACROS][NUM_MACROS];
    logic valid_partials [NUM_MACROS][NUM_MACROS];
    
    genvar i, j;
    generate
        for (i = 0; i < NUM_MACROS; i++) begin : gen_i
            for (j = 0; j < NUM_MACROS; j++) begin : gen_j
                multiplier u_mac (
                    .clk(clk),
                    .rst(rst),
                    .valid_in(valid_in),
                    .a(a[i*MACRO_WIDTH +: MACRO_WIDTH]),
                    .b(b[j*MACRO_WIDTH +: MACRO_WIDTH]),
                    .valid_out(valid_partials[i][j]),
                    .product(partial_products[i][j])
                );
            end
        end
    endgenerate

    // Accumulation stage (pipelined)
    logic [2*WIDTH-1:0] sum_stage1 [NUM_MACROS];
    logic valid_stage1 [NUM_MACROS];
    logic [2*WIDTH-1:0] row_sum [NUM_MACROS];
    
    always_comb begin
        for (int r = 0; r < NUM_MACROS; r++) begin
            row_sum[r] = '0;
            for (int c = 0; c < NUM_MACROS; c++) begin
                row_sum[r] = row_sum[r] + ({{(2*WIDTH - 2*MACRO_WIDTH){1'b0}}, partial_products[r][c]} << ((r+c)*MACRO_WIDTH));
            end
        end
    end
    
    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            for (int r = 0; r < NUM_MACROS; r++) begin
                sum_stage1[r] <= '0;
                valid_stage1[r] <= 1'b0;
            end
        end else begin
            for (int r = 0; r < NUM_MACROS; r++) begin
                sum_stage1[r] <= row_sum[r];
                valid_stage1[r] <= valid_partials[r][0]; // Assuming all valid_partials arrive at same time
            end
        end
    end
    
    logic [2*WIDTH-1:0] final_sum_comb;
    always_comb begin
        final_sum_comb = '0;
        for (int r = 0; r < NUM_MACROS; r++) begin
            final_sum_comb = final_sum_comb + sum_stage1[r];
        end
    end
    
    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            product <= '0;
            valid_out <= 1'b0;
        end else begin
            product <= final_sum_comb;
            valid_out <= valid_stage1[0];
        end
    end
endmodule
