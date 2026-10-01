load("@bazel-orfs//:openroad.bzl", "odb_debug")

# The design as ORFS runs it (design() parses config.mk), and the
# FLOW_VARIANT ladder's other two rungs (ladder.bzl). This BUILD, ladder.bzl
# and ladder_test.py are bazel-orfs's; ORFS gets config.mk, constraint.sdc,
# README.md and the sources.
load("@bazel_orfs_test_designs//:designs.bzl", "design")
load("@rules_python//python:py_test.bzl", "py_test")
load(":ladder.bzl", "ladder")

design(
    config = "config.mk",
    extra = ladder,
)

py_test(
    name = "ladder_test",
    srcs = ["ladder_test.py"],
    args = [
        "$(rootpath config.mk)",
        "$(rootpath ladder.bzl)",
    ],
    data = [
        "config.mk",
        "ladder.bzl",
    ],
)

# A persistent OpenROAD session on each rung's global route, the stage
# the README's numbers come from (tools/odb_debug/README.md).
[
    odb_debug(
        name = "tage_update{}_grt_odb_debug".format(suffix),
        src = ":tage_update{}_grt".format(suffix),
    )
    for suffix in [
        "_small",
        "_medium",
        "",
    ]
]
