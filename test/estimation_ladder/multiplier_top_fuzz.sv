// Fuzzable twin of multiplier_top.sv, for the CI-gate campaign.
//
// A separate module in a separate file, for the same reason
// multiplier_fuzz.sv is: wrapping fuzz knobs around the real top changed
// its netlist even with every knob at zero, because a generate block
// introduces a name scope and renaming nets is itself one of the
// perturbations under study. multiplier_top.sv therefore keeps its
// published netlist and this carries its own all-knobs-zero base.
//
// ---------------------------------------------------------------------
// What is held constant, and what deliberately is not
//
// The MACRO'S CONTENTS are constant: this instantiates the unchanged
// `multiplier`, hardened once as an abstract and reused by every variant.
// That is the realistic hierarchical case and it is free.
//
// The MACRO'S PLACEMENT is not held constant, and must not be. Macro
// placement is the biggest lever on top-level QoR and frequently the
// thing a change is trying to move, and nothing can tell us
// programmatically whether a given edit affects it. A gate that pinned it
// would be blind to exactly the class of change that matters most. So
// rtl_macro_placer runs for every variant and every perturbation, and its
// contribution to the spread is measured rather than removed.
//
// The gen_i/gen_j loops below are kept byte-identical to
// multiplier_top.sv so that macro INSTANCE NAMES are stable across
// variants. That is what makes macro displacement comparable between
// runs -- it is a measurement aid, not a constraint on the placer.
//
// ---------------------------------------------------------------------
// The knobs
//
//   FUZZ_TOP_ROWORDER  Accumulate each row in the reverse order.
//                      Equivalence-preserving: fixed-width unsigned
//                      addition is associative and commutative, so the
//                      sum is bit-identical. True effect on the achieved
//                      period: exactly zero.
//
//   FUZZ_TOP_TREE      Reduce the row sums as a balanced tree instead of
//                      a linear chain. Also equivalence-preserving, also
//                      exactly zero true effect -- and structurally very
//                      different. This is the variant most likely to move
//                      the macros, because it changes top-level
//                      connectivity and connectivity is what RTLMP
//                      clusters on.
//
//   EXTRA_TOP_STAGES   NOT equivalence-preserving, on purpose: the
//                      effect-size dial, N real logic levels on the
//                      accumulation path.
//
// Statement-order and identity-wire fuzzes are deliberately absent. On
// the multiplier design yosys canonicalised both away -- the timing
// fingerprint was identical to the base at every perturbation -- and here
// each variant costs a 900s flow run per perturbation to learn the same
// nothing. The reassociation fuzzes above are the ones that reached the
// netlist there, so they are what this uses.
//
// Parameter defaults come from defines so the flow can set them with
// VERILOG_DEFINES, while the module stays directly instantiable.
// ---------------------------------------------------------------------
`ifndef FUZZ_TOP_ROWORDER
`define FUZZ_TOP_ROWORDER 0
`endif
`ifndef FUZZ_TOP_TREE
`define FUZZ_TOP_TREE 0
`endif
`ifndef EXTRA_TOP_STAGES
`define EXTRA_TOP_STAGES 0
`endif

module multiplier_top_fuzz #(
    parameter int WIDTH = 128,
    parameter int MACRO_WIDTH = 32,
    parameter int FUZZ_TOP_ROWORDER = `FUZZ_TOP_ROWORDER,
    parameter int FUZZ_TOP_TREE = `FUZZ_TOP_TREE,
    parameter int EXTRA_TOP_STAGES = `EXTRA_TOP_STAGES
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

    // Byte-identical to multiplier_top.sv: the macro instance names this
    // produces are what macro displacement is measured against.
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

    // Same row sums, accumulated in one order or the other. Unsigned
    // addition of fixed-width values is associative and commutative, so
    // both arms produce bit-identical results and differ only in the
    // adder tree yosys builds.
    always_comb begin
        for (int r = 0; r < NUM_MACROS; r++) begin
            row_sum[r] = '0;
            if (FUZZ_TOP_ROWORDER == 0) begin
                for (int c = 0; c < NUM_MACROS; c++) begin
                    row_sum[r] = row_sum[r] +
                        ({{(2*WIDTH - 2*MACRO_WIDTH){1'b0}},
                          partial_products[r][c]} << ((r+c)*MACRO_WIDTH));
                end
            end else begin
                for (int c = NUM_MACROS - 1; c >= 0; c--) begin
                    row_sum[r] = row_sum[r] +
                        ({{(2*WIDTH - 2*MACRO_WIDTH){1'b0}},
                          partial_products[r][c]} << ((r+c)*MACRO_WIDTH));
                end
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
                valid_stage1[r] <= valid_partials[r][0];
            end
        end
    end

    // The final reduction: a linear chain, or a balanced tree. Same sum,
    // different depth and different connectivity between the macro
    // clusters -- which is the input RTLMP clusters on.
    logic [2*WIDTH-1:0] final_sum_comb;

    // Two structurally different reductions of the same values.
    //
    // Written as generate arms with their own signals rather than as
    // declarations inside a nested procedural block: yosys rejects
    // `automatic` declarations nested inside an always block ("Invalid
    // nesting of always blocks and/or initializations"), even though
    // that front end accepts them. Generate-scope signals are portable
    // across both. (A comment line may not begin with the word that names
    // the lint tool, or it is parsed as a directive.)
    generate
        if (FUZZ_TOP_TREE == 0 || (NUM_MACROS % 2) != 0) begin : g_chain
            always_comb begin
                final_sum_comb = '0;
                for (int r = 0; r < NUM_MACROS; r++) begin
                    final_sum_comb = final_sum_comb + sum_stage1[r];
                end
            end
        end else begin : g_tree
            // Pairwise first level, then a reduction over the halves.
            // For NUM_MACROS = 4 -- what this design uses -- that is
            // exactly a balanced binary tree, and for any even count it
            // is still a shallower and differently associated sum than
            // the chain, which is what the variant is for.
            logic [2*WIDTH-1:0] lvl1 [NUM_MACROS/2];

            always_comb begin
                for (int r = 0; r < NUM_MACROS / 2; r++) begin
                    lvl1[r] = sum_stage1[2*r] + sum_stage1[2*r + 1];
                end
            end

            always_comb begin
                final_sum_comb = '0;
                for (int r = 0; r < NUM_MACROS / 2; r++) begin
                    final_sum_comb = final_sum_comb + lvl1[r];
                end
            end
        end
    endgenerate

    // The effect-size dial. Add and xor alternate because a run of
    // additions of the same term reassociates into a constant-coefficient
    // multiply, which would make the chain shorter than it looks and the
    // dial non-monotone in the number of levels.
    logic [2*WIDTH-1:0] dial_out;

    always_comb begin
        logic [2*WIDTH-1:0] acc;
        logic [2*WIDTH-1:0] term;
        acc  = final_sum_comb;
        term = {{WIDTH{1'b0}}, a};
        for (int s = 0; s < EXTRA_TOP_STAGES; s++) begin
            if ((s % 2) == 0) begin
                acc = acc + term;
            end else begin
                acc = acc ^ term;
            end
        end
        dial_out = acc;
    end

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            product <= '0;
            valid_out <= 1'b0;
        end else begin
            product <= dial_out;
            valid_out <= valid_stage1[0];
        end
    end
endmodule
