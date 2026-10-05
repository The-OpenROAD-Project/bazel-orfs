"""Study arms for resistance-aware routing (study/tage-update-layers).

Each arm is the large rung with a few arguments changed, built as its
own variant so every arm stays cached and they compare side by side.
Not part of ORFS #4595: config.mk, ladder.bzl and ladder_test.py are.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load(":ladder.bzl", "LADDER", "ladder")

ARMS = {
    # A0: asap7's platform default, which #4595 inherited before M9
    "large_m7": {"arguments": {"MAX_ROUTING_LAYER": "M7"}},
    # A2: global route without resistance-aware layer assignment, which
    # asap7's platform config.mk turns on by default
    "large_ra0": {"arguments": {"ENABLE_RESISTANCE_AWARE": "0"}},
    # Ceilings for placement and CTS seeing the upper layers: every signal
    # wire timed at the M6/M7 or the M8/M9 RC until global route
    "large_rc67": {"sources": {"SET_RC_TCL": [":setRC_signal_m67.tcl"]}},
    "large_rc89": {"sources": {"SET_RC_TCL": [":setRC_signal_m89.tcl"]}},
}

def ladder_and_arms(name, platform, verilog_files, arguments, user_arguments, sources, user_sources, user_stages, macros, stage_data, tags):
    ladder(name, platform, verilog_files, arguments, user_arguments, sources, user_sources, user_stages, macros, stage_data, tags)
    for variant, changes in ARMS.items():
        orfs_flow(
            name = name,
            variant = variant,
            verilog_files = verilog_files,
            pdk = "//flow:" + platform,
            arguments = arguments | {"VERILOG_TOP_PARAMS": LADDER["large"]} | changes.get("arguments", {}),
            user_arguments = user_arguments,
            sources = sources | changes.get("sources", {}),
            user_sources = user_sources,
            user_stages = user_stages,
            macros = macros,
            stage_data = stage_data,
            tags = tags + ["manual"],
        )
