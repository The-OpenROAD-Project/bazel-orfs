"""The global floorplan planner's Bazel side: extract, plan, consume."""

load("//:openroad.bzl", "orfs_run")

def floorplan_extract(name, src, arguments = {}, timing = True, tags = ["manual"], visibility = None):
    """A synthesised block's facts for the planner: `<name>.block.json`.

    One OpenROAD action on the block's synthesis (extract_block.tcl, a
    tab-separated dump) and one Python action (block_json.py); both are
    cached on the synthesis ODB, so only a changed block reruns. Declare
    it in the package of `src` (orfs_run's RESULTS_DIR is the declaring
    package's).

    Args:
        name: the target; writes `<name>.block.json`
        src: the block's `_synth` target
        arguments: the block flow's floorplan variables (CORE_UTILIZATION,
            CORE_ASPECT_RATIO, CORE_MARGIN, DIE_AREA, ...), which its
            synthesis stage does not carry: the outline its flow will
            draw (die_rule) is computed from them
        timing: False skips the boundary timing sweeps
        tags: forwarded
        visibility: forwarded
    """
    orfs_run(
        name = name + "_dump",
        src = src,
        outs = [name + ".dump.tsv"],
        script = Label("//tools/floorplan:extract_block.tcl"),
        tags = tags,
        user_arguments = {
            "EXTRACT_" + k: v
            for k, v in arguments.items()
        } | {
            "EXTRACT_OUT": "$(location %s.dump.tsv)" % name,
            "EXTRACT_TIMING": "1" if timing else "0",
        },
    )
    native.genrule(
        name = name,
        srcs = [":%s_dump" % name],
        outs = [name + ".block.json"],
        cmd = "$(execpath %s) $< $@" % Label("//tools/floorplan:block_json"),
        tools = [Label("//tools/floorplan:block_json")],
        tags = tags,
        visibility = visibility,
    )

def floorplan_pdk(name, src, tags = ["manual"], visibility = None):
    """A platform's wire model for the planner: `<name>.pdk.json`.

    Per routing layer the unit RC setRC.tcl installs and the optimally
    repeated wire's ps/um from the resizer's buffer-wire delay. Any
    synthesis of the platform serves as `src`; declare it in its package.

    Args:
        name: the target; writes `<name>.pdk.json`
        src: a `_synth` target of the platform
        tags: forwarded
        visibility: forwarded
    """
    orfs_run(
        name = name + "_dump",
        src = src,
        outs = [name + ".pdk_dump.tsv"],
        script = Label("//tools/floorplan:extract_pdk.tcl"),
        tags = tags,
        user_arguments = {
            "EXTRACT_OUT": "$(location %s.pdk_dump.tsv)" % name,
        },
    )
    native.genrule(
        name = name,
        srcs = [":%s_dump" % name],
        outs = [name + ".pdk.json"],
        cmd = "$(execpath %s) $< $@" % Label("//tools/floorplan:pdk_json"),
        tools = [Label("//tools/floorplan:pdk_json")],
        tags = tags,
        visibility = visibility,
    )
