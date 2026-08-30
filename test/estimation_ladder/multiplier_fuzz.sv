// Fuzzable twin of multiplier.sv, for the seed-sensitivity study.
//
// A separate file and a separate module on purpose.  Wrapping the fuzz
// knobs around the real multiplier turned out to change its netlist even
// with every knob at zero -- a generate block introduces a name scope,
// which renames nets, which is itself one of the perturbations under
// study (Kahng & Mantik's "ordering and naming" class).  Measured: the
// ground-truth sample went from 54 near-critical paths to 59.  That would
// have silently invalidated every number already published in README.md,
// which is exactly the kind of quiet baseline shift this study exists to
// detect.  So multiplier.sv keeps its published netlist and the fuzz
// family lives here with its own base -- all-knobs-zero -- against which
// the variants are compared.
//
// ---------------------------------------------------------------------
// What the knobs are for
//
// The study needs RTL edits whose TRUE effect on the design is known, so
// a measured effect can be judged against it.  Two kinds, and the
// difference between them is the point:
//
//   FUZZ_ORDER, FUZZ_ALIAS   Equivalence-preserving.  The module computes
//                            bit-for-bit the same function; only the
//                            SystemVerilog yosys reads differs.  The true
//                            effect on the achieved period is therefore
//                            ZERO, so whatever the flow or the estimator
//                            reports for these is noise by construction.
//                            This is Kahng & Reda's zero-change netlist
//                            transformation (ISPD 2005) lifted to RTL.
//
//   FUZZ_SPLIT               Equivalence-preserving but restructured:
//                            a*b as (a_hi*b << H) + a_lo*b, algebraically
//                            identical and structurally quite different.
//                            The most realistic of the three -- a
//                            developer rewriting an expression and
//                            expecting no PPA change -- and the only one
//                            that hands synthesis genuinely different
//                            logic to optimise.
//
//   EXTRA_ADD_STAGES         NOT equivalence-preserving, on purpose: the
//                            coarse effect-size dial.  N extra logic
//                            levels in series ahead of the product
//                            register.  Measured on multiplier, N=2/4/8
//                            moved the flow's achieved period by
//                            -2.2%/+8.1%/+51.3% -- note the sign at N=2:
//                            adding logic made it faster, so the dial is
//                            not monotone.
//
//   EXTRA_LOAD_BITS          The FINE dial, added because every setting of
//                            the coarse one landed far above the flow's
//                            own 1.24% perturbation spread, which is
//                            precisely the regime that cannot be tested
//                            that way.  One XOR level on the LOW N bits of
//                            the result only: the critical path through a
//                            multiplier runs through the high bits, so
//                            small N should perturb the period barely at
//                            all.  The point is not to predict the effect
//                            but to obtain a family of small ones, and to
//                            let the flow ensemble measure what each
//                            actually is.
//
// Parameter defaults come from defines so the flow can set them with
// VERILOG_DEFINES (-D FUZZ_ORDER=1), while the module stays directly
// instantiable with explicit parameters.
// ---------------------------------------------------------------------
`ifndef FUZZ_ORDER
`define FUZZ_ORDER 0
`endif
`ifndef FUZZ_ALIAS
`define FUZZ_ALIAS 0
`endif
`ifndef FUZZ_SPLIT
`define FUZZ_SPLIT 0
`endif
`ifndef EXTRA_ADD_STAGES
`define EXTRA_ADD_STAGES 0
`endif
`ifndef EXTRA_LOAD_BITS
`define EXTRA_LOAD_BITS 0
`endif

module multiplier_fuzz #(
    parameter int WIDTH = 32,
    parameter int FUZZ_ORDER = `FUZZ_ORDER,
    parameter int FUZZ_ALIAS = `FUZZ_ALIAS,
    parameter int FUZZ_SPLIT = `FUZZ_SPLIT,
    parameter int EXTRA_ADD_STAGES = `EXTRA_ADD_STAGES,
    parameter int EXTRA_LOAD_BITS = `EXTRA_LOAD_BITS
) (
    input  logic                 clk,
    input  logic                 rst,
    input  logic                 valid_in,
    input  logic [WIDTH-1:0]     a,
    input  logic [WIDTH-1:0]     b,
    output logic                 valid_out,
    output logic [2*WIDTH-1:0]   product
);

    // Stage 1: Register inputs.
    logic [WIDTH-1:0] a_reg, b_reg;
    logic             v1_reg;

    // Two whole processes rather than a constant-folded branch inside one,
    // so what differs is the order the assignments are elaborated in
    // rather than a condition the front end folds away and forgets.
    // Nonblocking assignments within a block are order-independent, so
    // both arms describe the same circuit.
    generate
        if (FUZZ_ORDER == 0) begin : g_order_ab
            always_ff @(posedge clk or posedge rst) begin
                if (rst) begin
                    a_reg  <= '0;
                    b_reg  <= '0;
                    v1_reg <= 1'b0;
                end else begin
                    a_reg  <= a;
                    b_reg  <= b;
                    v1_reg <= valid_in;
                end
            end
        end else begin : g_order_ba
            always_ff @(posedge clk or posedge rst) begin
                if (rst) begin
                    v1_reg <= 1'b0;
                    b_reg  <= '0;
                    a_reg  <= '0;
                end else begin
                    v1_reg <= valid_in;
                    b_reg  <= b;
                    a_reg  <= a;
                end
            end
        end
    endgenerate

    // The operands as the multiply sees them.  FUZZ_ALIAS routes them
    // through identity wires, which synthesis should remove entirely --
    // an edit that provably cannot change the circuit, and so the
    // cleanest possible zero-effect change.
    logic [WIDTH-1:0] a_mul, b_mul;

    generate
        if (FUZZ_ALIAS == 0) begin : g_direct
            assign a_mul = a_reg;
            assign b_mul = b_reg;
        end else begin : g_alias
            logic [WIDTH-1:0] a_id, b_id;
            assign a_id  = a_reg;
            assign b_id  = b_reg;
            assign a_mul = a_id;
            assign b_mul = b_id;
        end
    endgenerate

    // The multiply, either as one operator or split algebraically.
    logic [2*WIDTH-1:0] mul_result;

    generate
        if (FUZZ_SPLIT == 0 || (WIDTH % 2) != 0) begin : g_mul_plain
            assign mul_result = a_mul * b_mul;
        end else begin : g_mul_split
            // a = a_hi*2**H + a_lo, so a*b = (a_hi*b << H) + a_lo*b.
            // Operands are zero-extended to 2*WIDTH by concatenation
            // rather than a size cast, so this does not depend on how far
            // the front end's SystemVerilog support reaches.  The true
            // product fits in 2*WIDTH bits, so nothing truncates and the
            // result is bit-for-bit equal to the plain form.
            localparam int H = WIDTH / 2;
            logic [2*WIDTH-1:0] a_hi, a_lo, b_full, hi_prod, lo_prod;
            assign a_hi       = {{(WIDTH + H){1'b0}}, a_mul[WIDTH-1:H]};
            assign a_lo       = {{(2 * WIDTH - H){1'b0}}, a_mul[H-1:0]};
            assign b_full     = {{WIDTH{1'b0}}, b_mul};
            assign hi_prod    = a_hi * b_full;
            assign lo_prod    = a_lo * b_full;
            assign mul_result = (hi_prod << H) + lo_prod;
        end
    endgenerate

    // The effect-size dial.  Alternating add and xor rather than a chain
    // of adds: repeated addition of the same term reassociates into a
    // constant-coefficient multiply, which would make the chain shorter
    // than it looks and the dial non-monotone.  Mixing the two leaves
    // nothing to reassociate, so N really is N logic levels.
    //
    // Written as one always_comb over a local accumulator rather than a
    // chained array: an unpacked array indexed across generate blocks is
    // tracked at whole-array granularity by some front ends, which then
    // report the chain as circular combinational logic (verilator
    // UNOPTFLAT) even though each element is written exactly once.  A
    // blocking accumulator says the same thing with no ambiguity.
    logic [2*WIDTH-1:0] dial_out;

    always_comb begin
        logic [2*WIDTH-1:0] acc;
        logic [2*WIDTH-1:0] term;
        acc  = mul_result;
        term = {{WIDTH{1'b0}}, b_mul};
        for (int s = 0; s < EXTRA_ADD_STAGES; s++) begin
            if ((s % 2) == 0) begin
                acc = acc + term;
            end else begin
                acc = acc ^ term;
            end
        end
        dial_out = acc;
    end

    // The fine dial: one XOR level on the low EXTRA_LOAD_BITS bits.  Those
    // bits are not normally on the critical path of a multiplier, so this
    // is real logic whose effect on the period should be small -- which is
    // the range the coarse dial cannot reach.
    logic [2*WIDTH-1:0] fine_out;

    always_comb begin
        fine_out = dial_out;
        for (int i = 0; i < EXTRA_LOAD_BITS; i++) begin
            fine_out[i] = dial_out[i] ^ a_mul[i % WIDTH];
        end
    end

    // Stage 2: Multiply result.
    logic [2*WIDTH-1:0] prod_reg;
    logic               v2_reg;

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            prod_reg <= '0;
            v2_reg   <= 1'b0;
        end else begin
            prod_reg <= fine_out;
            v2_reg   <= v1_reg;
        end
    end

    // Stage 3: Output register.
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
