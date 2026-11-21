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

def floorplan_netlist(name, src, tags = ["manual"], visibility = None):
    """A synthesised block's netlist for rungs 1 and 2: `<name>.netlist.json`
    and, target `<name>_tangle`, `<name>.tangle.json` (tangle.py: groups of
    tangled logic, net range, mutual contraction; minutes).

    extract_netlist.tcl dumps the signal netlist from the block's
    synthesis; netlist.py fits Rent's p and k by recursive bisection and
    measures each port bus's cone. Both cached on the synthesis ODB.
    Declare it in the package of `src`.

    Args:
        name: the target; writes `<name>.netlist.json`
        src: the block's `_synth` target
        tags: forwarded
        visibility: forwarded
    """
    orfs_run(
        name = name + "_netlist_dump",
        src = src,
        outs = [name + ".netlist.tsv"],
        script = Label("//tools/floorplan:extract_netlist.tcl"),
        tags = tags,
        user_arguments = {
            "EXTRACT_OUT": "$(location %s.netlist.tsv)" % name,
        },
    )
    native.genrule(
        name = name,
        srcs = [":%s_netlist_dump" % name],
        outs = [name + ".netlist.json"],
        cmd = "$(execpath %s) $< $@" % Label("//tools/floorplan:netlist"),
        tools = [Label("//tools/floorplan:netlist")],
        tags = tags,
        visibility = visibility,
    )
    native.genrule(
        name = name + "_tangle",
        srcs = [":%s_netlist_dump" % name],
        outs = [name + ".tangle.json"],
        cmd = "$(execpath %s) $< $@" % Label("//tools/floorplan:tangle"),
        tools = [Label("//tools/floorplan:tangle")],
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

def floorplan_plan(
        name,
        blocks,
        pdk,
        cut,
        constraints,
        calibration = None,
        parent = None,
        netlists = [],
        tangles = [],
        run_all = False,
        tags = ["manual"],
        visibility = None):
    """The planner's verdict on a cut, and its floorplan when it fits.

    Writes `<name>/verdict.json`, `<name>/verdict.md` and
    `<name>/floorplan.json` ({} when the cut is infeasible). The action
    succeeds either way: the verdict is its result, and a test reads it.
    Only the JSONs are inputs, so a changed constraint reruns the plan
    alone, in seconds.

    Args:
        name: the target
        blocks: the floorplan_extract targets, one per macro
        pdk: the floorplan_pdk target
        cut: cut.json, which block each macro is
        constraints: constraints.json
        calibration: the design's limits per rung, each with its source
            (plan.py's CALIBRATION_KEYS); a rung without one measures and
            fails nothing
        parent: the parent's crossings (parent.json), optional
        netlists: floorplan_netlist targets, for rung 1, optional
        tangles: their `_tangle` targets, for rung 2, optional
        run_all: every rung past the first stop
        tags: forwarded
        visibility: forwarded
    """
    srcs = blocks + netlists + tangles + [pdk, cut, constraints] + ([parent] if parent else []) + ([calibration] if calibration else [])
    args = " ".join(["--block $(execpath %s)" % b for b in blocks] + ["--netlist $(execpath %s)" % n for n in netlists] + ["--tangle $(execpath %s)" % t for t in tangles])
    args += " --pdk $(execpath %s) --cut $(execpath %s) --constraints $(execpath %s)" % (pdk, cut, constraints)
    if parent:
        args += " --parent $(execpath %s)" % parent
    if calibration:
        args += " --calibration $(execpath %s)" % calibration
    if run_all:
        args += " --all"
    native.genrule(
        name = name,
        srcs = srcs,
        outs = [
            name + "/verdict.json",
            name + "/verdict.md",
            name + "/floorplan.json",
        ],
        cmd = ("$(execpath {plan}) {args} --verdict $(execpath {n}/verdict.json) " +
               "--verdict-md $(execpath {n}/verdict.md) --floorplan $(execpath {n}/floorplan.json)").format(
            plan = Label("//tools/floorplan:plan"),
            args = args,
            n = name,
        ),
        tools = [Label("//tools/floorplan:plan")],
        tags = tags,
        visibility = visibility,
    )

def floorplan_parent(name, src, blocks = [], timing = True, tags = ["manual"], visibility = None):
    """The parent's crossings for the planner: `<name>.parent.json`.

    extract_parent.tcl on the parent's hierarchical synthesis
    (OPENROAD_HIERARCHICAL=1, the blocks kept modules anywhere below the
    top), then parent_json.py. Declare it in the package of `src`.

    Args:
        name: the target; writes `<name>.parent.json`
        src: the parent's `_synth` target
        blocks: the blocks' modules; the top's own children when empty
        timing: False skips the glue's delays (no timing update)
        tags: forwarded
        visibility: forwarded
    """
    orfs_run(
        name = name + "_dump",
        src = src,
        outs = [name + ".parent_dump.tsv"],
        script = Label("//tools/floorplan:extract_parent.tcl"),
        tags = tags,
        user_arguments = {
            "EXTRACT_BLOCKS": " ".join(blocks),
            "EXTRACT_OUT": "$(location %s.parent_dump.tsv)" % name,
            "EXTRACT_TIMING": "1" if timing else "0",
        },
    )
    native.genrule(
        name = name,
        srcs = [":%s_dump" % name],
        outs = [name + ".parent.json"],
        cmd = "$(execpath %s) $< $@" % Label("//tools/floorplan:parent_json"),
        tools = [Label("//tools/floorplan:parent_json")],
        tags = tags,
        visibility = visibility,
    )

def floorplan_consume(name, plan, macros, tags = ["manual"], visibility = None):
    """What the flows read from a plan's floorplan.json.

    Per macro M: `<name>_M.args.json` (an extra_arguments JSON with its
    DIE_AREA and CORE_AREA, for its floorplan stage), `<name>_M_pins.tcl`
    (its IO_CONSTRAINTS, a set_io_pin_constraint per bus) and
    `<name>_M_guidance.tcl` (set_macro_guidance_region per hard object, for
    a flow that opts in). For the parent: `<name>_parent.args.json` and
    `<name>_place_macros.tcl` (its MACRO_PLACEMENT_TCL). An infeasible
    plan fails these actions, naming its verdict.

    Args:
        name: prefix of the targets
        plan: the floorplan_plan target
        macros: the plan's macro names
        tags: forwarded
        visibility: forwarded
    """
    emit = Label("//tools/floorplan:emit")
    fp = "%s/floorplan.json" % plan
    for m in macros:
        native.genrule(
            name = "%s_%s_files" % (name, m),
            srcs = [fp],
            outs = [
                "%s_%s.args.json" % (name, m),
                "%s_%s_pins.tcl" % (name, m),
                "%s_%s_guidance.tcl" % (name, m),
            ],
            cmd = ("$(execpath {emit}) block $(execpath {fp}) {m} --args $(execpath {n}_{m}.args.json) " +
                   "--pins $(execpath {n}_{m}_pins.tcl) --guidance $(execpath {n}_{m}_guidance.tcl)").format(
                emit = emit,
                fp = fp,
                m = m,
                n = name,
            ),
            tools = [emit],
            tags = tags,
            visibility = visibility,
        )
    native.genrule(
        name = "%s_parent_files" % name,
        srcs = [fp],
        outs = [
            "%s_parent.args.json" % name,
            "%s_place_macros.tcl" % name,
        ],
        cmd = "$(execpath {emit}) parent $(execpath {fp}) --args $(execpath {n}_parent.args.json) --place $(execpath {n}_place_macros.tcl)".format(
            emit = emit,
            fp = fp,
            n = name,
        ),
        tools = [emit],
        tags = tags,
        visibility = visibility,
    )
