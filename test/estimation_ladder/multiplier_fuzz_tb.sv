// Do the equivalence-preserving fuzz knobs in multiplier_fuzz.sv actually
// preserve equivalence?
//
// The seed-sensitivity study's premise is that FUZZ_ORDER, FUZZ_ALIAS and
// FUZZ_SPLIT have a TRUE effect of exactly zero -- so whatever the flow or
// the estimator reports for them is noise -- while EXTRA_ADD_STAGES is a
// real change.  Everything the study concludes rests on that, so it is
// checked rather than asserted.
//
// WHAT THIS IS NOT.  Random vectors cannot prove equivalence; they can
// only fail to disprove it.  This is a smoke check, not a proof, and the
// study is not a place where a false equivalence claim would be obvious
// -- it would show up as a "noise" reading that was really signal.  A
// proper logical equivalence check (a commercial LEC) is the
// belts-and-suspenders step, and is worth doing before any of this is
// relied on beyond the exploratory result it currently supports.
//
// Not wired into bazel: it needs a simulator that is not one of this
// repo's hermetic dependencies.  Run it by hand:
//
//   $ verilator --binary --quiet -Wno-DECLFILENAME -Wno-WIDTHEXPAND \
//     -Wno-WIDTHTRUNC --top-module tb -o fuzzcheck \
//     test/estimation_ladder/multiplier_fuzz_tb.sv \
//     test/estimation_ladder/multiplier_fuzz.sv && ./obj_dir/fuzzcheck
//
// Last run: checks=1995 equivalence_errors=0 dial_differed=1995.
module tb;
    localparam int W = 32;
    logic clk = 0, rst = 1, vin = 0;
    logic [W-1:0] a, b;

    logic [2*W-1:0] p_base, p_order, p_alias, p_split, p_dial;
    logic vo_base, vo_order, vo_alias, vo_split, vo_dial;

    multiplier_fuzz #(.WIDTH(W)) u_base
        (.clk, .rst, .valid_in(vin), .a, .b, .valid_out(vo_base), .product(p_base));
    multiplier_fuzz #(.WIDTH(W), .FUZZ_ORDER(1)) u_order
        (.clk, .rst, .valid_in(vin), .a, .b, .valid_out(vo_order), .product(p_order));
    multiplier_fuzz #(.WIDTH(W), .FUZZ_ALIAS(1)) u_alias
        (.clk, .rst, .valid_in(vin), .a, .b, .valid_out(vo_alias), .product(p_alias));
    multiplier_fuzz #(.WIDTH(W), .FUZZ_SPLIT(1)) u_split
        (.clk, .rst, .valid_in(vin), .a, .b, .valid_out(vo_split), .product(p_split));
    multiplier_fuzz #(.WIDTH(W), .EXTRA_ADD_STAGES(4)) u_dial
        (.clk, .rst, .valid_in(vin), .a, .b, .valid_out(vo_dial), .product(p_dial));

    int errors = 0;
    int dial_differs = 0;
    int checks = 0;

    initial begin
        repeat (4) begin #1 clk = ~clk; end
        rst = 0;
        for (int i = 0; i < 2000; i++) begin
            a = {$urandom, $urandom};
            b = {$urandom, $urandom};
            vin = $urandom_range(0, 1);
            #1 clk = 1; #1 clk = 0;
            if (i > 4) begin
                checks++;
                // The three equivalence-preserving knobs must match the
                // base exactly, product and valid alike.
                if (p_order !== p_base || vo_order !== vo_base) errors++;
                if (p_alias !== p_base || vo_alias !== vo_base) errors++;
                if (p_split !== p_base || vo_split !== vo_base) errors++;
                // The dial must NOT match: it is a real change, and a dial
                // that silently computed the same thing would measure
                // nothing while looking like it measured something.
                if (p_dial !== p_base) dial_differs++;
            end
        end
        $display("checks=%0d equivalence_errors=%0d dial_differed=%0d", checks, errors, dial_differs);
        if (errors != 0)
            $display("FAIL: an equivalence-preserving knob changed the function");
        else if (dial_differs == 0)
            $display("FAIL: EXTRA_ADD_STAGES did not change the function; it is not a dial");
        else
            $display("PASS: 3 knobs equivalence-preserving, dial is a real change");
        $finish;
    end
endmodule
