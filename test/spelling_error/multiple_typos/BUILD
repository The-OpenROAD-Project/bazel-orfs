# Multiple unknown variables in a single call.
# Expected error listing both: CORE_UTILIZATON, PLACE_DENSTY

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "multiple_typos",
    arguments = {
        "CORE_UTILIZATON": "20",
        "PLACE_DENSTY": "0.5",
    },
    verilog_files = ["//:rtl/dummy.v"],
)
