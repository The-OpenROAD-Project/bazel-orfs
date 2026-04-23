# Multiple known ORFS variables placed in user_arguments.
# Expected: both are listed, sorted, in the shadow error.

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "user_args_multiple_shadow",
    user_arguments = {
        "PLACE_DENSITY": "0.5",
        "CORE_UTILIZATION": "20",
    },
    verilog_files = ["//:rtl/dummy.v"],
)
