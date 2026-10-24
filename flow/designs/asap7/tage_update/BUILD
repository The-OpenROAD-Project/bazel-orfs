load("@bazel-orfs//:openroad.bzl", "odb_debug")

# The design as ORFS runs it, base and the FLOW_VARIANT ladder's other
# two rungs, small and large, all from config.mk (design() parses each
# variant). This BUILD is bazel-orfs's; ORFS gets config.mk,
# constraint.sdc, README.md and the sources.
load("@bazel_orfs_test_designs//:designs.bzl", "design")

design(
    config = "config.mk",
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
        "",
        "_large",
    ]
]
