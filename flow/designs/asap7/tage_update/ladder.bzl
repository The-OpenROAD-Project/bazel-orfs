"""The FLOW_VARIANT ladder of config.mk as bazel-orfs flows.

ORFS selects a rung with `make FLOW_VARIANT=small|medium|large`, and
base, the default variant, is the rung named by BASE. bazel-orfs's
config.mk parser evaluates one variant, base, so the other two rungs
are added here through design()'s `extra` hook, from the same processed
arguments with VERILOG_TOP_PARAMS replaced. ladder_test checks that LADDER
and BASE say what config.mk's ifeq blocks say.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")

LADDER = {
    "small": "TABLES 2 BANKS 1 WAYS 1 MBTB_BANKS 1 MBTB_WAYS 1",
    "medium": "TABLES 4 BANKS 2 WAYS 2 MBTB_BANKS 2 MBTB_WAYS 2",
    "large": "TABLES 8 BANKS 4 WAYS 2 MBTB_BANKS 4 MBTB_WAYS 4",
}

# the smallest rung that shows the effect; config.mk's else branch
BASE = "medium"

def ladder(name, platform, verilog_files, arguments, user_arguments, sources, user_sources, user_stages, macros, stage_data, tags):
    for variant, params in LADDER.items():
        if variant == BASE:
            # base is this rung already; a second copy would build the
            # same design again under another variant directory
            continue
        orfs_flow(
            name = name,
            variant = variant,
            verilog_files = verilog_files,
            pdk = "//flow:" + platform,
            arguments = arguments | {"VERILOG_TOP_PARAMS": params},
            user_arguments = user_arguments,
            sources = sources,
            user_sources = user_sources,
            user_stages = user_stages,
            macros = macros,
            stage_data = stage_data,
            tags = tags,
        )
