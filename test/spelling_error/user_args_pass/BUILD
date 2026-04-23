# user_arguments bypasses variables.yaml spell-check.
# Expected: package loads without errors.

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "user_args_pass",
    arguments = {
        "CORE_UTILIZATION": "20",
    },
    user_arguments = {
        "MY_PROJECT_KNOB": "42",
        "ARRAY_COLS": "4",
    },
    verilog_files = ["//:rtl/dummy.v"],
)
