# Test-fixture plumbing, not a designs tree of bazel-orfs's own.
#
# The config.mk DSL (private/orfs_design.bzl) is what every ORFS design
# goes through, and it is hard-wired to ORFS's layout: a design lives at
# flow/designs/<platform>/<design>/ and its PDK is //flow:<platform>. To
# exercise that path in this repository in seconds -- rather than only
# against real ORFS designs that take minutes -- the fixtures under
# flow/designs/ mirror the layout, and this package supplies the PDK
# labels by aliasing ORFS's. See //test:dsl_* and test/BUILD.
alias(
    name = "asap7",
    actual = "@orfs//flow:asap7",
    visibility = ["//flow/designs:__subpackages__"],
)
