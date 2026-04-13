# Typo in arguments key: CORE_UTILIZATON (missing I).
# Expected error: Unknown ORFS variable(s) in arguments: CORE_UTILIZATON

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "argument_typo",
    arguments = {
        "CORE_UTILIZATON": "20",
    },
    verilog_files = ["//:rtl/dummy.v"],
)
