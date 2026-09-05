load("@bazel_orfs_test_designs//:designs.bzl", "design")

# The same two lines every ORFS design package has, bound to this
# repository's fixture DESIGNS. Visible to //test, where the tests live.
design(
    config = "config.mk",
    visibility = ["//test:__pkg__"],
)
