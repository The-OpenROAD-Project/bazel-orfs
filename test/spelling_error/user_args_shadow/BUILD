# user_arguments must not shadow a known ORFS variable.
# Expected error: user_arguments contains known ORFS variable(s): CORE_UTILIZATION

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "user_args_shadow",
    user_arguments = {
        "CORE_UTILIZATION": "20",
    },
    verilog_files = ["//:rtl/dummy.v"],
)
