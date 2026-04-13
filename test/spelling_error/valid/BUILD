# Control case: all variable names are correct.
# Expected: package loads without errors.

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "valid",
    arguments = {
        "CORE_UTILIZATION": "20",
        "PLACE_DENSITY": "0.5",
    },
    sources = {
        "SDC_FILE": ["//:rtl/dummy.v"],
    },
    verilog_files = ["//:rtl/dummy.v"],
)
