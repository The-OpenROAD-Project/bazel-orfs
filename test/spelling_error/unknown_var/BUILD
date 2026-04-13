# Completely fabricated variable name.
# Expected error: Unknown ORFS variable(s) in arguments: TOTALLY_FAKE_VAR

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "unknown_var",
    arguments = {
        "TOTALLY_FAKE_VAR": "1",
    },
    verilog_files = ["//:rtl/dummy.v"],
)
