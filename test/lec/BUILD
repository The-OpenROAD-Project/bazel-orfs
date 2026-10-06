load(":lec.bzl", "lec_test")

# The wrapper's own check: an equivalent pair passes, and a pair that
# differs is reported as different (kepler-formal exits 0 either way).
lec_test(
    name = "equivalent_test",
    frontend = "sv",
    gate_verilog_files = ["and_or_demorgan.v"],
    gold_verilog_files = ["and_or.v"],
)

lec_test(
    name = "difference_test",
    expect_equivalent = False,
    frontend = "sv",
    gate_verilog_files = ["and_or_wrong.v"],
    gold_verilog_files = ["and_or.v"],
)

# The gate-level path (combinational LEC on liberty cells), which also
# logs the problem size the solver was given (patches/kepler-formal-0001).
lec_test(
    name = "cells_equivalent_test",
    expect_problem_size = True,
    gate_verilog_files = ["and_or_cells_ao.v"],
    gold_verilog_files = ["and_or_cells.v"],
    liberty_files = [
        ":asap7_ao.lib",
        ":asap7_simple.lib",
    ],
)

# kepler-formal reads liberty uncompressed.
[genrule(
    name = "asap7_" + kind,
    srcs = ["@orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_%s_RVT_FF_nldm_211120.lib.gz" % kind.upper()],
    outs = ["asap7_%s.lib" % kind],
    cmd = "gunzip -c $< > $@",
) for kind in [
    "ao",
    "simple",
]]
