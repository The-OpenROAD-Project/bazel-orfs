# Typo in sources key: SDC_FLIE (transposed letters).
# Expected error: Unknown ORFS variable(s) in sources: SDC_FLIE

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "source_typo",
    sources = {
        "SDC_FLIE": ["//:rtl/dummy.v"],
    },
    verilog_files = ["//:rtl/dummy.v"],
)
