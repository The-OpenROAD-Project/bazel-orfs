module mock_cpu #(
    parameter int NUM_CORES      = 2,   // Parallelism
    parameter int PIPELINE_DEPTH = 4,   // Latency
    parameter int WORK_PER_STAGE = 8,   // Logic Depth
    parameter int DATA_WIDTH     = 32   
)(
    input  logic                    clk,
    input  logic [DATA_WIDTH-1:0]   data_in,
    output logic [DATA_WIDTH-1:0]   data_out
);

    // 1. Input Registration (Isolates timing from external input delay)
    logic [DATA_WIDTH-1:0] data_in_reg;
    
    always_ff @(posedge clk) begin
        data_in_reg <= data_in;
    end

    // Aggregate outputs from all cores
    logic [DATA_WIDTH-1:0] core_results [NUM_CORES];

    genvar c, s, w;
    generate
        for (c = 0; c < NUM_CORES; c++) begin : g_cores
            
            // Pipeline stages (+1 for the initial stage coming from input reg)
            logic [DATA_WIDTH-1:0] stage_regs [PIPELINE_DEPTH+1];
            
            // Connect input register to first stage with unique core seed
            assign stage_regs[0] = data_in_reg + c; 

            for (s = 0; s < PIPELINE_DEPTH; s++) begin : g_pipeline
                logic [DATA_WIDTH-1:0] stage_logic;

                always_comb begin
                    stage_logic = stage_regs[s];
                    // "Mock Compute": Chains of XOR/ADD to create logic depth
                    for (int w = 0; w < WORK_PER_STAGE; w++) begin
                        stage_logic = (stage_logic ^ (stage_logic << 1)) + (w * s);
                    end
                end

                // Pipeline Register (No Reset)
                always_ff @(posedge clk) begin
                    stage_regs[s+1] <= stage_logic;
                end
            end

            assign core_results[c] = stage_regs[PIPELINE_DEPTH];
        end
    endgenerate

    // 2. Output Reduction (Combinational)
    logic [DATA_WIDTH-1:0] data_out_comb;
    always_comb begin
        data_out_comb = '0;
        for (int i = 0; i < NUM_CORES; i++) begin
            data_out_comb ^= core_results[i];
        end
    end

    // 3. Output Registration (Isolates timing from external output load)
    always_ff @(posedge clk) begin
        data_out <= data_out_comb;
    end

endmodule
