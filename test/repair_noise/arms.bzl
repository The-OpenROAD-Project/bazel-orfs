"""ORFS designs as ORFS has them, each through global route in four arms:
base, a placement seed change, floorplan repair_timing skipped and CTS
repair_timing skipped (ORFS #4893)."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@orfs_designs//:designs.bzl", "DESIGNS")
load("//private:stages.bzl", "split_user_variables")

def _orfs(labels):
    """DESIGNS' labels are ORFS's own, relative to its repository."""
    return ["@orfs" + x if x.startswith("//") else x for x in labels]

ARMS = {
    "base": {},
    "seed2": {"GPL_RANDOM_SEED": "2"},
    "fp_skip": {"SKIP_FLOORPLAN_REPAIR_TIMING": "1"},
    "cts_skip": {"SKIP_CTS_REPAIR_TIMING": "1"},
    "both_skip": {"SKIP_FLOORPLAN_REPAIR_TIMING": "1", "SKIP_CTS_REPAIR_TIMING": "1"},
}

def repair_arms(key):
    """<top>_<arm>_grt and <top>_<arm>_grt_report for one ORFS design.

    Args:
        key: the DESIGNS key, "<platform>/<design>".
    """
    d = DESIGNS[key]
    if d["blocks"]:
        fail(key + ": BLOCKS designs are not handled here")
    sources = {k: _orfs(v) for k, v in d["sources"].items()}
    arguments = dict(d["arguments"])
    if arguments.get("SYNTH_HIERARCHICAL") == "1" and "SYNTH_NUM_PARTITIONS" not in arguments:
        arguments["SYNTH_NUM_PARTITIONS"] = "32"
    frontend = arguments.get("SYNTH_HDL_FRONTEND", "")
    arguments["SYNTH_HDL_FRONTEND"] = frontend

    # as orfs_design(): an include directory reaches synthesis as data
    includes = [
        "@orfs//" + x.strip().rstrip("/") + ":include"
        for x in arguments.get("VERILOG_INCLUDE_DIRS", "").replace("\t", " ").split(" ")
        if x.strip() and not x.strip().startswith("external/")
    ]
    if includes:
        # ORFS's paths are relative to its own root; from this package
        # they are found under the @orfs repository in the execroot.
        arguments["VERILOG_INCLUDE_DIRS"] = " ".join([
            "external/+orfs_repositories+orfs/" + x.strip()
            for x in arguments["VERILOG_INCLUDE_DIRS"].split(" ")
            if x.strip()
        ])
    arguments, user_arguments = split_user_variables(arguments)
    sources, user_sources = split_user_variables(sources)
    for arm, extra in ARMS.items():
        orfs_flow(
            name = d["name"],
            arguments = arguments | extra,
            last_stage = "grt",
            pdk = "@orfs//flow:" + d["platform"],
            sources = sources,
            user_arguments = user_arguments,
            user_sources = user_sources,
            stage_data = {"synth": includes} if includes else {},
            tags = ["manual"],
            variant = key.replace("/", "_").replace("-", "_") + "_" + arm,
            verilog_files = _orfs([f for f in d["verilog_files"] if "$(" not in f]),
            yosys_frontend_reason = None if frontend == "slang" else "measured as ORFS runs %s" % key,
        )

def _sources_for(key):
    d = DESIGNS[key]
    sources = {k: _orfs(v) for k, v in d["sources"].items()}
    return sources

def two_pass_arms(key):
    """Pass 2 of the two-pass study, from the base arm's floorplan.

    two_pass_probe_<v>: on the base arm's grt, the clock latency of each
    register clock pin and the slack of each output pin, three ways.
    <top>_<v>_tp_ctl_grt: pass 2 with nothing fed back (must equal base).
    <top>_<v>_tp_clk_grt: pass 2, pass 1's latencies set during global
    placement. <top>_<v>_tp_vcts_grt: one pass, global placement's own
    virtual clock tree (-virtual_cts) as the reference estimate.

    Args:
        key: the DESIGNS key, "<platform>/<design>".
    """
    d = DESIGNS[key]
    v = key.replace("/", "_").replace("-", "_")
    base = d["name"] + "_" + v + "_base"
    arguments = dict(d["arguments"])
    if arguments.get("SYNTH_HIERARCHICAL") == "1" and "SYNTH_NUM_PARTITIONS" not in arguments:
        arguments["SYNTH_NUM_PARTITIONS"] = "32"
    frontend = arguments.get("SYNTH_HDL_FRONTEND", "")
    arguments["SYNTH_HDL_FRONTEND"] = frontend
    if "VERILOG_INCLUDE_DIRS" in arguments:
        arguments["VERILOG_INCLUDE_DIRS"] = " ".join([
            "external/+orfs_repositories+orfs/" + x.strip()
            for x in arguments["VERILOG_INCLUDE_DIRS"].replace("\t", " ").split(" ")
            if x.strip()
        ])
    for k in ["PRE_GLOBAL_PLACE_TCL", "GLOBAL_PLACEMENT_ARGS"]:
        if k in arguments or k in d["sources"]:
            fail(key + ": sets " + k + ", which the two-pass arms own")
    arguments, user_arguments = split_user_variables(arguments)
    sources, user_sources = split_user_variables(_sources_for(key))

    probe = "two_pass_probe_" + v
    orfs_run(
        name = probe,
        src = ":" + base + "_grt",
        outs = [probe + "_latencies.tsv", probe + "_slacks.tsv"],
        arguments = arguments,
        script = "two_pass_probe.tcl",
        sources = sources,
        tags = ["manual"],
        user_arguments = user_arguments | {
            "OUTPUT_LATENCIES": "$(location %s_latencies.tsv)" % probe,
            "OUTPUT_SLACKS": "$(location %s_slacks.tsv)" % probe,
        },
        user_sources = user_sources | {
            "STAGE_SRC_TCL": ["//test/pre_route_pessimism:stage_src.tcl"],
        },
        variant = probe,
    )

    arms = {
        "tp_ctl": ({}, {}, {}),
        "tp_clk": (
            {},
            {"PRE_GLOBAL_PLACE_TCL": ["two_pass_latency.tcl"]},
            {"TWO_PASS_LATENCIES": [":" + probe + "_latencies.tsv"]},
        ),
        "tp_vcts": ({"GLOBAL_PLACEMENT_ARGS": "-virtual_cts"}, {}, {}),
    }
    for arm, (extra, extra_sources, extra_user_sources) in arms.items():
        orfs_flow(
            name = d["name"],
            arguments = arguments | extra,
            last_stage = "grt",
            pdk = "@orfs//flow:" + d["platform"],
            previous_stage = {"place": ":" + base + "_floorplan"},
            sources = sources | extra_sources,
            user_arguments = user_arguments,
            user_sources = user_sources | extra_user_sources,
            tags = ["manual"],
            variant = v + "_" + arm,
            verilog_files = _orfs([f for f in d["verilog_files"] if "$(" not in f]),
            yosys_frontend_reason = None if frontend == "slang" else "measured as ORFS runs %s" % key,
        )
