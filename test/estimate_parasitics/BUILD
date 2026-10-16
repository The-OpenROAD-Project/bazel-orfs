load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("//:openroad.bzl", "orfs_run")

# ORFS's generate_abstract.tcl on copies of gcd's results: OpenROAD picks
# the parasitics, and 6_final is timed with 6_final.spef when the final
# stage extracted it, never because a .spef file exists. Patches 0136
# (OpenROAD) and 0137 (ORFS).

# name: (stage, SPEF, EXPECT, extra arguments)
CASES = {
    # The final stage extracted parasitics: the abstract is timed with them.
    "final_reads_extracted_spef": ("final", "extracted", "spef", {}),
    # The final stage extracted parasitics but the SPEF is gone: an error,
    # not an estimate.
    "final_missing_spef_fails": ("final", "missing", "error", {}),
    # The final stage did not extract parasitics: a SPEF left behind by
    # another run is never read.
    "final_leftover_spef_unread": (
        "final",
        "leftover",
        "global_routing",
        {"COPY_SKIPPED_DETAILED_ROUTE": "1"},
    ),
    # An abstract from global route is timed with the route's parasitics,
    # and a SPEF beside it is never read.
    "grt_uses_global_routes": ("grt", "leftover", "global_routing", {}),
}

[orfs_run(
    name = "gcd_{}_{}".format(platform, name),
    src = "@orfs//flow/designs/{}/gcd:gcd_{}".format(platform, stage),
    outs = ["gcd_{}_{}.ok".format(platform, name)],
    script = ":abstract_case.tcl",
    user_arguments = {
        key: value
        for arguments in [
            {
                "EXPECT": expect,
                "OUTPUT": "gcd_{}_{}.ok".format(platform, name),
                "SPEF": spef,
            },
            extra,
        ]
        for key, value in arguments.items()
    },
) for platform in [
    "asap7",
    "nangate45",
] for name, (stage, spef, expect, extra) in CASES.items()]

build_test(
    name = "estimate_parasitics_test",
    targets = [
        ":gcd_{}_{}".format(platform, name)
        for platform in [
            "asap7",
            "nangate45",
        ]
        for name in CASES
    ],
)
