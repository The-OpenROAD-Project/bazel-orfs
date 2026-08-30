// Do the equivalence-preserving top-level fuzz knobs actually preserve
// equivalence?
//
// The campaign reads a measured effect for FUZZ_TOP_ROWORDER and
// FUZZ_TOP_TREE as pure noise, because their true effect on the achieved
// period is supposed to be exactly zero. If that were wrong the study
// would report signal as noise and nothing would look amiss -- so it is
// checked before any 900s flow run is paid for.
//
// WHAT THIS IS NOT. Random vectors cannot prove equivalence, only fail to
// disprove it. This is a smoke check. A proper logical equivalence check
// is the belts-and-suspenders step and is worth doing before these
// results are relied on beyond the exploratory conclusions they support.
//
// Not wired into bazel: it needs a simulator that is not one of this
// repo's hermetic dependencies. Run it by hand:
//
//   $ verilator --binary --quiet -Wno-DECLFILENAME -Wno-WIDTHEXPAND \
//     -Wno-WIDTHTRUNC -Wno-UNOPTFLAT --top-module tb_top -o topcheck \
//     test/estimation_ladder/multiplier_top_fuzz_tb.sv \
//     test/estimation_ladder/multiplier_top_fuzz.sv \
//     test/estimation_ladder/multiplier.sv && ./obj_dir/topcheck
module tb_top;
    localparam int W = 128;
    logic clk = 0, rst = 1, vin = 0;
    logic [W-1:0] a, b;

    logic [2*W-1:0] p_base, p_roworder, p_tree, p_dial;
    logic vo_base, vo_roworder, vo_tree, vo_dial;

    multiplier_top_fuzz #(.WIDTH(W)) u_base (
        .clk, .rst, .valid_in(vin), .a, .b,
        .valid_out(vo_base), .product(p_base));

    multiplier_top_fuzz #(.WIDTH(W), .FUZZ_TOP_ROWORDER(1)) u_roworder (
        .clk, .rst, .valid_in(vin), .a, .b,
        .valid_out(vo_roworder), .product(p_roworder));

    multiplier_top_fuzz #(.WIDTH(W), .FUZZ_TOP_TREE(1)) u_tree (
        .clk, .rst, .valid_in(vin), .a, .b,
        .valid_out(vo_tree), .product(p_tree));

    multiplier_top_fuzz #(.WIDTH(W), .EXTRA_TOP_STAGES(4)) u_dial (
        .clk, .rst, .valid_in(vin), .a, .b,
        .valid_out(vo_dial), .product(p_dial));

    int errors = 0;
    int dial_differed = 0;
    int checks = 0;

    initial begin
        repeat (4) begin #1 clk = ~clk; end
        rst = 0;
        for (int n = 0; n < 500; n++) begin
            a = {$urandom, $urandom, $urandom, $urandom};
            b = {$urandom, $urandom, $urandom, $urandom};
            vin = $urandom_range(0, 1);
            #1 clk = 1; #1 clk = 0;
            if (n > 6) begin
                checks++;
                if (p_roworder !== p_base || vo_roworder !== vo_base) errors++;
                if (p_tree !== p_base || vo_tree !== vo_base) errors++;
                // The dial must NOT match: a dial that silently computed
                // the same thing would measure nothing while looking like
                // it measured something.
                if (p_dial !== p_base) dial_differed++;
            end
        end
        $display("checks=%0d equivalence_errors=%0d dial_differed=%0d",
                 checks, errors, dial_differed);
        if (errors != 0)
            $display("FAIL: an equivalence-preserving knob changed the function");
        else if (dial_differed == 0)
            $display("FAIL: EXTRA_TOP_STAGES did not change the function");
        else
            $display("PASS: roworder and tree equivalence-preserving, dial is real");
        $finish;
    end
endmodule
