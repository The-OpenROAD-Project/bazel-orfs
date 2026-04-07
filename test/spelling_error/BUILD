# Manual test: intentional spelling error to verify variable validation.
# Run: bazelisk build //test/spelling_error:spelling_error_test_synth
# Expected: build failure with "Unknown ORFS variable(s)" message.
# This package is separate so the load-time failure does not block
# other targets in //test.

load("//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "spelling_error_test",
    arguments = {
        "CORE_UTILIZATON": "20",
    },
    tags = ["manual"],
    verilog_files = ["//test:rtl/lb_32x128_top.v"],
)
