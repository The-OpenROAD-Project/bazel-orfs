load("//:lec.bzl", "lec_test")

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
