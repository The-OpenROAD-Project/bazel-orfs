"""One campaign arm: a flow variant plus the probes that measure it.

The five axes of this study -- size, shape, wire-RC layer, placement seed
and repair policy -- differ only in which arguments they vary and which
probes they read. Written out longhand that was five near-identical
comprehensions over `orfs_flow` and `orfs_run`, about seven hundred lines
of repetition in which a single mistyped argument would be invisible.

`study_arm()` is that pattern once. What an axis supplies is a name, the
arguments that make it different, and the probes worth running on it.

Every target is manual: an arm is a flow run.
"""

load("//:openroad.bzl", "orfs_flow", "orfs_run")

# Probe script -> the stage whose ODB it reads. `size` also needs the
# stage logs, which is why it is listed separately below.
PROBES = {
    "ladder": ("stage_ladder.tcl", False),
    "layers": ("layer_usage.tcl", False),
    "size": ("size_probe.tcl", True),
}

def study_arm(
        name,
        design,
        arguments,
        user_arguments = {},
        sources = {},
        user_sources = {},
        verilog_files = [],
        top = None,
        probes = ["ladder"],
        probe_stages = ["grt"],
        out_prefix = {},
        previous_stage = {},
        last_stage = "grt",
        visibility = None):
    """Declare one arm and its probe runs.

    Args:
        name: arm name; targets are `<name>` for the flow and
            `<probe>_<name>[_<stage>]` for each probe run.
        design: the parsed DESIGNS entry the arm is built from, so an
            arm can never disagree with the design it measures.
        arguments: ORFS variables that make this arm different.
        user_arguments: project-specific variables, exempt from the
            variables.yaml spell-check.
        sources: source-typed ORFS variables.
        user_sources: source-typed project hooks; the staging preamble
            and the shared path sampler are added to these.
        verilog_files: forwarded to orfs_flow.
        top: Verilog top, defaulting to the design's own.
        probes: which of PROBES to run.
        out_prefix: per-probe override for the output file's prefix.
            Passed explicitly by the axes whose result names the analysis
            scripts already parse, so factoring these arms into one macro
            cannot quietly rename what a re-run produces.
        probe_stages: which stages to run the ladder probe on. The other
            probes read grt, since that is where guides and the final
            per-stage timings are.
        previous_stage: share a prefix with another arm rather than
            re-running it -- the reason a 36-leaf ensemble is affordable.
        last_stage: how far the flow runs.
        visibility: forwarded.
    """
    orfs_flow(
        name = name,
        arguments = arguments,
        last_stage = last_stage,
        previous_stage = previous_stage,
        sources = sources,
        tags = ["manual"],
        top = top or design["name"],
        user_arguments = user_arguments,
        verilog_files = verilog_files,
        visibility = visibility,
    )

    probe_sources = user_sources | {
        "EXTRACT_LIB_TCL": ["//test/estimation_ladder:extract_lib.tcl"],
        "STAGE_SRC_TCL": ["stage_src.tcl"],
    }

    for probe in probes:
        script, needs_logs = PROBES[probe]
        stages = probe_stages if probe == "ladder" else ["grt"]
        for stage in stages:
            prefix = out_prefix.get(probe, probe)
            target = "{}_{}_{}".format(prefix, name, stage)
            out = target + ".json"
            orfs_run(
                name = target,
                src = ":{}_{}".format(name, stage),
                outs = [out],
                arguments = arguments,
                script = script,
                sources = sources,
                src_logs = needs_logs,
                tags = ["manual"],
                user_arguments = user_arguments | {
                    "OUTPUT_JSON": "$(location {})".format(out),
                },
                user_sources = probe_sources,
                variant = target,
            )
