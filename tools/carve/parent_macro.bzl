"""The parent as a macro: the parent and its blocks built side by side from one plan, checked flat by a top level that dissolves them."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@bazel-orfs//tools/carve:memories.bzl", "carve_memories")
load("@rules_shell//shell:sh_test.bzl", "sh_test")

def parent_macro_flow(
        name,
        top,
        plan,
        plan_pins,
        place_macros,
        blocks,
        verilog_files,
        arguments,
        sources,
        user_arguments = {},
        user_sources = {},
        user_stages = {},
        stage_arguments = {},
        top_arguments = {},
        top_sources = {},
        macros = [],
        clock_port = "clock",
        block_clocks = ["clock"],
        budget_ps = "2000",
        max_skew_ps = "20",
        report_budget_ps = None,
        plan_budget = "1500000",
        top_level_arguments = {},
        top_level_user_arguments = {},
        whole_check = False,
        headroom_sets = "",
        headroom_skip = "",
        top_flat_user_arguments = {},
        top_flat_check_ps = None,
        ledger = False,
        ledger_user_arguments = {},
        variant = None,
        pdk = "//flow:asap7",
        tags = ["manual"]):
    """The parent as a macro, its blocks, and the flat top level that checks the carve.

    The plan in git is all the parent and the blocks share: the blocks'
    outlines and places and every block pin (plan_floorplan.py's
    <block>_pins.tcl, clock pins included). The blocks build from their
    pin files; the parent, <name>_<stage>, builds from the same files and
    nothing of a block's, so all of them build side by side to global
    route, each its own fast signal, and only the top level,
    <name>_pm_<stage>, waits for all of them.

    The parent is the design's own RTL with the blocks blackboxes,
    cut out in synthesis (evert.tcl: each block pin a port
    u_<block>__<pin>, the instance gone), on the plan's die with a hole
    per block (parent_holes.tcl). <name>_abstract is its LEF with
    exact shapes, <name>_timing_model its timing model.

    The top level is the parent and the blocks, instances only
    (top_netlist.tcl), each placed by the plan and dissolved into the
    cells, nets and route guides of its own global route, its clock tree
    left behind (top_dissolve.tcl): the cells stay fixed where their
    macro put them; <name>_pm_top (top_level.tcl) builds one clock tree
    over every register and routes the stitches and the clock.

    The crossing report: every reg2reg path not contained in one macro
    that needs more than budget_ps, each cell on it by name, timed in
    sets of macros that fit memory. <name>_pm_crossing_plan finds the
    sets (crossing_plan.tcl), <name>_pm_crossing_sets cuts each to its
    crossing cones and writes it with its parasitics as SPEF,
    <name>_pm_crossing_time times each in a process of its own, and
    <name>_pm_crossings merges them: crossing.txt, tables.md and
    histogram.svg.

    The crossing ledger (ledger = True) is the same question asked
    without a top level: <name>_pm_<part>_ledger reads each part's halves
    of its boundary pins at the part's own global route
    (crossing_ledger.tcl), and <name>_pm_ledger sums them along each
    crossing net (crossing_ledger.py): ledger/crossings.txt and
    ledger/summary.txt.

    Args:
      name: the parent macro's flow; the top level is <name>_pm.
      top: the design's top module, the parent macro's module.
      plan: the PLAN dict plan_floorplan.py wrote.
      plan_pins: {block: its plan pins file}.
      place_macros: the plan's place_macros.tcl: the parent's own
        macros and placed netlists where the plan put them.
      blocks: {block: {"abstract": its abstract target, "grt": its
        global route target}}.
      verilog_files: the design's RTL, the blocks' included.
      arguments: the parent macro's arguments.
      sources: the parent macro's sources.
      user_arguments: the parent macro's user arguments; a
        SYNTH_POST_HIERARCHY_SCRIPTS among them runs before evert.ys.
      user_sources: the parent macro's user sources.
      user_stages: the parent macro's user stages.
      stage_arguments: the parent macro's per-stage arguments, over
        arguments (orfs_flow's stage_arguments).
      top_arguments: the top level's arguments, over the defaults.
      top_sources: the top level's sources, over the defaults
        (SDC_FILE at least).
      macros: the parent's own macros.
      clock_port: the design's clock port.
      block_clocks: the blocks' clock pins, by name.
      budget_ps: the longest reg2reg path, ps, that may cross a macro
        boundary.
      max_skew_ps: the top level's clock skew it stops over, ps.
      report_budget_ps: the crossing report's budget, ps; budget_ps by
        default.
      plan_budget: instances a crossing set may hold, the measure of
        its memory.
      top_level_arguments: ORFS variables for top_level.tcl's runs
        (SKIP_PIN_ACCESS).
      top_level_user_arguments: top_level.tcl's own settings
        (TOP_DPL_ARGS, TOP_GRT_ITERATIONS, TOP_PARASITICS).
      whole_check: time the top level whole too, <name>_pm_crossing_whole,
        and test that the sets report the same paths,
        <name>_pm_crossing_test; for a design small enough to time whole.
      headroom_sets: the crossing sets <name>_pm_crossing_headroom
        measures, their numbers separated by spaces; empty: every set.
      headroom_skip: the measurements it skips, of: wire vt skew cycles.
      top_flat_user_arguments: top_level.tcl's settings for
        <name>_pm_top_flat, the top level that takes its macros' boundary
        logic over (TOP_FLATTEN); whole_check only.
      top_flat_check_ps: the period <name>_pm_top_flat_test checks: the
        top level as built fails it, the flattened one passes it, and no
        macro's own paths get worse.
      ledger: the crossing ledger, <name>_pm_ledger; with whole_check,
        <name>_pm_ledger_test checks it against the paths the top level
        times through each crossing net, with the parent's spot checks
        and its count of pins over the boundary budgets, and
        <name>_pm_ledger_negative_test that a part's halves left out are
        missed.
      ledger_user_arguments: crossing_ledger.tcl's settings for every
        part: the boundary budgets its pins are counted over
        (LEDGER_IN2REG_PS, LEDGER_REG2OUT_PS, LEDGER_IN2OUT_PS) and the
        others its header lists.
      variant: the parent macro's variant, when another flow of the
        package has the same top module; its targets are then
        <name>_<variant>_<stage>, and <name>_<variant> stands for <name>
        above.
      pdk: the PDK.
      tags: forwarded.
    """
    base = name + ("_" + variant if variant else "")
    names = sorted(blocks.keys())
    clocks = " ".join(block_clocks)
    holes = []
    for b in names:
        p = plan["macros"][b]
        _, _, x1, y1 = p["DIE_AREA"].split(" ")
        holes.append("%s %s %s %s %s" % (b, p["x_um"], p["y_um"], x1, y1))
    pins = [plan_pins[b] for b in names]

    parent_sources = dict(sources)
    parent_sources["IO_CONSTRAINTS"] = ["@bazel-orfs//tools/carve:parent_holes.tcl"]
    parent_sources["MACRO_PLACEMENT_TCL"] = [place_macros]

    # evert.ys runs evert.tcl by its path in the workspace, after the
    # design's own hook scripts
    hooks = user_arguments.get("SYNTH_POST_HIERARCHY_SCRIPTS", "")
    parent_user_arguments = user_arguments | {
        "CARVE_BLOCKS": " ".join(names),
        "CARVE_CLOCKS": clocks,
        "CARVE_TOP": top,
        "HOLES": " ".join(holes),
        "PLAN_BLOCKS_ELSEWHERE": "1",
        "SYNTH_POST_HIERARCHY_SCRIPTS": (hooks + " tools/carve/evert.ys").strip(),
    }
    parent_user_sources = user_sources | {
        "CARVE_EVERT": [
            "@bazel-orfs//tools/carve:evert.tcl",
            "@bazel-orfs//tools/carve:evert.ys",
        ],
        "PLAN_PINS": pins,
    }

    # the plan reaches the floorplan only: a new plan does not
    # synthesize the parent again
    floorplan = ["floorplan"]
    parent_user_stages = user_stages | {
        "CARVE_BLOCKS": ["synth", "floorplan"],
        "CARVE_CLOCKS": ["synth"],
        "CARVE_EVERT": ["synth"],
        "CARVE_TOP": ["synth"],
        "HOLES": floorplan,
        "PLAN_BLOCKS_ELSEWHERE": floorplan,
        "PLAN_PINS": floorplan,
        "SYNTH_POST_HIERARCHY_SCRIPTS": ["synth"],
    }
    orfs_flow(
        name = name,
        top = top,
        arguments = {
            # by default the first flush through grt, for turnaround:
            # XSTile_parent's CTS setup repair ground for over an hour at
            # WNS -437 ps without moving it, on the 4771 x 2064 um die. A
            # design's arguments or stage_arguments turn repair back on.
            "SKIP_CTS_REPAIR_TIMING": "1",
            "SKIP_INCREMENTAL_REPAIR": "1",
        } | arguments | {
            "CORE_AREA": plan["parent"]["CORE_AREA"],
            "DIE_AREA": plan["parent"]["DIE_AREA"],
            "OPENROAD_HIERARCHICAL": "0",
            "SYNTH_BLACKBOXES": " ".join(names),
        },
        last_stage = "grt",
        macros = macros,
        pdk = pdk,
        sources = parent_sources,
        stage_arguments = stage_arguments,
        variant = variant,
        tags = tags,
        user_arguments = parent_user_arguments,
        user_sources = parent_user_sources,
        user_stages = parent_user_stages,
        verilog_files = verilog_files,
    )

    # the LEF and the timing model apart: the top level reads only the
    # LEF, the parent being dissolved at its floorplan, and XSTile's
    # parent's timing model was an hour on one core
    orfs_run(
        name = "%s_abstract" % base,
        src = ":%s_grt" % base,
        outs = ["%s/%s.lef" % (base, top)],
        cmd = "run",
        script = "@bazel-orfs//test/abutment:abstract_exact.tcl",
        tags = tags,
        user_arguments = {"LEF_OUT": "$(location %s/%s.lef)" % (base, top)},
    )
    orfs_run(
        name = "%s_timing_model" % base,
        src = ":%s_grt" % base,
        # named as orfs_headroom drops a block's own model
        outs = ["%s/%s_typ.lib" % (base, top)],
        cmd = "run",
        script = "@bazel-orfs//test/abutment:abstract_exact.tcl",
        tags = tags,
        user_arguments = {"LIB_OUT": "$(location %s/%s_typ.lib)" % (base, top)},
    )

    # the plan's pin partner dump, from the parent's synthesis alone
    orfs_run(
        name = "%s_pin_partners" % base,
        src = ":%s_synth" % base,
        outs = ["%s/pin_partners.txt" % base],
        script = "@bazel-orfs//tools/carve:parent_pin_partners.tcl",
        tags = tags,
        user_arguments = {
            "CARVE_BLOCKS": " ".join(names),
            "PROBE_OUT": "$(location %s/pin_partners.txt)" % base,
        },
    )

    # the memories inside every macro the top level dissolves: the
    # masters its dissolve copies cells of (ODB-1221), and their timing
    carve_memories(
        name = "%s_memories" % base,
        srcs = [":%s_grt" % base] + [blocks[b]["grt"] for b in names],
        lef = "%s/memories.lef" % base,
        lib = "%s/memories.lib" % base,
        tags = tags,
    )

    pm = "%s_pm" % base
    orfs_run(
        name = "%s_top_netlist" % base,
        src = ":%s_synth" % base,
        outs = ["%s/%s.v" % (base, pm)],
        script = "@bazel-orfs//tools/carve:top_netlist.tcl",
        tags = tags,
        user_arguments = {
            "CARVE_BLOCKS": " ".join(names),
            "CARVE_CLOCKS": clocks,
            "CLOCK_PORT": clock_port,
            "TOP_NAME": pm,
            "TOP_V": "$(location %s/%s.v)" % (base, pm),
        },
        user_sources = {"PLAN_PINS": pins},
    )

    # the top level, flat: every macro dissolved at its own global route
    odbs = []
    for b in [top] + names:
        src = ":%s_grt" % base if b == top else blocks[b]["grt"]
        native.filegroup(
            name = "%s_%s_grt_odb" % (pm, b),
            srcs = [src],
            output_group = "5_1_grt.odb",
            tags = tags,
        )
        odbs.append(":%s_%s_grt_odb" % (pm, b))
        if ledger:
            # the part's halves of every crossing, at its own global route
            orfs_run(
                name = "%s_%s_ledger" % (pm, b),
                src = src,
                outs = ["%s/ledger/parts/%s.txt" % (pm, b)],
                cmd = "run",
                script = "@bazel-orfs//tools/carve:crossing_ledger.tcl",
                tags = tags,
                user_arguments = ledger_user_arguments | {
                    "LEDGER_OUT": "$(location %s/ledger/parts/%s.txt)" % (pm, b),
                },
                user_sources = {"HR_TCL": ["@bazel-orfs//tools/odb_debug:headroom.tcl"]},
            )
    orfs_flow(
        name = pm,
        arguments = {
            # the parent is a macro the size of the die until it is
            # dissolved, and the floorplan refuses a macro larger than the
            # core (IFP-0002): the core is the die, and top_dissolve.tcl
            # makes the rows on the parent's core once it is gone
            "CORE_AREA": plan["parent"]["DIE_AREA"],
            "DIE_AREA": plan["parent"]["DIE_AREA"],
            "DONT_BUFFER_PORTS": "1",
            "MACRO_ROWS_HALO_X": "0",
            "MACRO_ROWS_HALO_Y": "0",
            "SYNTH_HIERARCHICAL": "0",
        } | top_arguments,
        # the floorplan dissolves the macros; the clock tree and global
        # route are top_level.tcl's (<pm>_top below): ORFS's place, CTS
        # and global route optimise cells, and every cell here is fixed
        last_stage = "floorplan",
        macros = [blocks[b]["abstract"] for b in names] + macros,
        pdk = pdk,
        sources = {
            "ADDITIONAL_LEFS": [":%s/%s.lef" % (base, top), ":%s/memories.lef" % base],
            "ADDITIONAL_LIBS": [":%s/memories.lib" % base],
            "IO_CONSTRAINTS": ["@bazel-orfs//test/abutment:io_top.tcl"],
            "MACRO_PLACEMENT_TCL": ["@bazel-orfs//tools/carve:top_dissolve.tcl"],
            "SYNTH_NETLIST_FILES": [":%s/%s.v" % (base, pm)],
            # the macros brought their own tap cells
            "TAPCELL_TCL": ["@bazel-orfs//tools/carve:no_tapcells.tcl"],
        } | top_sources,
        tags = tags,
        user_arguments = {
            "DISSOLVE_MASTERS": " ".join([top] + names),
            "HOLES": " ".join(holes),
            "PARENT_CORE_AREA": plan["parent"]["CORE_AREA"],
            "PARENT_INST": "u_parent",
        },
        user_sources = {
            "DISSOLVE_ODBS": odbs,
            "PLAN_PINS": pins,
        },
        verilog_files = [],
    )

    _top_level(
        pm,
        budget_ps = report_budget_ps or budget_ps,
        max_skew_ps = max_skew_ps,
        plan_budget = plan_budget,
        top_level_arguments = top_level_arguments,
        top_level_user_arguments = top_level_user_arguments,
        whole_check = whole_check,
        headroom_sets = headroom_sets,
        headroom_skip = headroom_skip,
        top_flat_user_arguments = top_flat_user_arguments,
        top_flat_check_ps = top_flat_check_ps,
        tags = tags,
    )
    if ledger:
        _ledger(
            pm,
            top = top,
            blocks = names,
            budget_ps = budget_ps,
            max_skew_ps = max_skew_ps,
            top_level_user_arguments = top_level_user_arguments,
            whole_check = whole_check,
            tags = tags,
        )

def _ledger(pm, top, blocks, budget_ps, max_skew_ps, top_level_user_arguments, whole_check, tags):
    """The crossing ledger joined, and its check against the top level.

    Args:
      pm: the top level's flow.
      top: the parent macro's module, the hub.
      blocks: the blocks, by module.
      budget_ps: the period a crossing may need, ps.
      max_skew_ps: the clock check's limit, ps, and the most a path's
        clock may add to what the ledger holds of it.
      top_level_user_arguments: top_level.tcl's own settings.
      whole_check: check the ledger against the top level timed whole.
      tags: forwarded.
    """
    hub = ":%s/ledger/parts/%s.txt" % (pm, top)
    parts = {b: ":%s/ledger/parts/%s.txt" % (pm, b) for b in blocks}
    native.genrule(
        name = "%s_ledger" % pm,
        srcs = [hub] + parts.values(),
        outs = ["%s/ledger/%s" % (pm, f) for f in ["crossings.txt", "summary.txt"]],
        cmd = "$(location @bazel-orfs//tools/carve:crossing_ledger) --hub $(location %s) %s --budget %s --out $$(dirname $(location %s/ledger/crossings.txt))" % (
            hub,
            " ".join(["--block %s=$(location %s)" % (b, parts[b]) for b in blocks]),
            budget_ps,
            pm,
        ),
        tools = ["@bazel-orfs//tools/carve:crossing_ledger"],
        tags = tags,
    )

    if not whole_check:
        return

    # the ledger's reference, on a design small enough for a path search
    # per crossing net: the paths the routed top level times through each
    top_level = ":%s_top" % pm
    orfs_run(
        name = "%s_ledger_top" % pm,
        src = ":%s_floorplan" % pm,
        outs = ["%s/ledger/top.txt" % pm],
        cmd = "run",
        data = [top_level],
        script = "@bazel-orfs//tools/carve:top_level.tcl",
        tags = tags,
        user_arguments = top_level_user_arguments | {
            "CROSSING_TXT": "$(location %s/ledger/top.txt)" % pm,
            "MAX_SKEW_PS": max_skew_ps,
            "TOP_DIR": "$(location %s)" % top_level,
            "TOP_FROM": "grt",
        },
        user_sources = {
            "CLOCK_CHECK": ["@bazel-orfs//tools/carve:top_clock_check.tcl"],
            "CROSSING_PATHS": ["@bazel-orfs//tools/carve:crossing_ledger_top.tcl"],
        },
    )

    # the ledger's check: no path the top level times through a crossing
    # net needs more than the net's halves sum to, and each net's slowest
    # needs as much; and the negative control: a block's halves at zero,
    # or its ledger gone, and the check fails, by that block's name
    check = "@bazel-orfs//tools/carve:crossing_ledger_check"
    ledgers = [
        "$(rootpath :%s/ledger/top.txt)" % pm,
        "$(rootpath %s)" % hub,
    ] + ["%s=$(rootpath %s)" % (b, parts[b]) for b in blocks]
    for test, control in [("ledger_test", "-"), ("ledger_negative_test", "all")]:
        sh_test(
            name = "%s_%s" % (pm, test),
            srcs = ["@bazel-orfs//tools/carve:crossing_ledger_check.sh"],
            args = ["$(rootpath %s)" % check, control, max_skew_ps] + ledgers,
            data = [":%s/ledger/top.txt" % pm, hub, check] + parts.values(),
            tags = tags,
        )

def _top_level(pm, budget_ps, max_skew_ps, plan_budget, top_level_arguments, top_level_user_arguments, whole_check, headroom_sets, headroom_skip, top_flat_user_arguments, top_flat_check_ps, tags):
    """The top level's clock tree and global route, and its crossing report.

    Args:
      pm: the top level's flow, at its floorplan.
      budget_ps: the crossing report's budget, ps.
      max_skew_ps: the clock check's limit, ps.
      plan_budget: instances a crossing set may hold.
      top_level_arguments: ORFS variables for top_level.tcl's runs.
      top_level_user_arguments: top_level.tcl's own settings.
      whole_check: time the top level whole too and test the sets
        against it.
      headroom_sets: the crossing sets the headroom measures.
      headroom_skip: the measurements the headroom skips.
      top_flat_user_arguments: top_level.tcl's settings for the top level
        that takes its macros' boundary logic over (whole_check only).
      top_flat_check_ps: the period the flattened top level's test checks.
      tags: forwarded.
    """
    scripts = {
        "CLOCK_CHECK": ["@bazel-orfs//tools/carve:top_clock_check.tcl"],
        "CROSSING_CONES": ["@bazel-orfs//tools/carve:crossing_cones.tcl"],
        "CROSSING_PATHS": ["@bazel-orfs//tools/carve:crossing_paths.tcl"],
        "CROSSING_TIME": ["@bazel-orfs//tools/carve:crossing_time.tcl"],
    }
    top_arguments = {
        # one tree over every register of every macro: on the toy
        # (test/parent_macro) clusters of 10 sinks took the setup skew
        # from 37.4 to 17.9 ps, the default's 30 left it at 37.4
        "CTS_CLUSTER_SIZE": "10",
        # the macros' routes kept, the clock tree and the stitches routed
        # (patch 0173)
        "GLOBAL_ROUTE_ARGS": "-allow_congestion -verbose -unguided_only",
    } | top_level_arguments
    top = ":%s_top" % pm

    # floorplan to global route: the routed top level, 5_top_grt.odb
    orfs_run(
        name = "%s_top" % pm,
        src = ":%s_floorplan" % pm,
        out_dir = "%s/top" % pm,
        cmd = "run",
        script = "@bazel-orfs//tools/carve:top_level.tcl",
        arguments = top_arguments,
        tags = tags,
        user_arguments = top_level_user_arguments | {"MAX_SKEW_PS": max_skew_ps},
        user_sources = scripts,
    )

    # the sets: every path's signature held by one
    orfs_run(
        name = "%s_crossing_plan" % pm,
        src = ":%s_floorplan" % pm,
        outs = ["%s/sets.txt" % pm, "%s/signatures.txt" % pm],
        cmd = "run",
        data = [top],
        script = "@bazel-orfs//tools/carve:crossing_plan.tcl",
        tags = tags,
        user_arguments = {
            "CROSSING_SETS": "$(location %s/sets.txt)" % pm,
            "CROSSING_SIGNATURES": "$(location %s/signatures.txt)" % pm,
            "PLAN_BUDGET": plan_budget,
            "TOP_DIR": "$(location %s)" % top,
        },
    )

    # each set cut to its crossing cones, written with its parasitics
    orfs_run(
        name = "%s_crossing_sets" % pm,
        src = ":%s_floorplan" % pm,
        out_dir = "%s/sets" % pm,
        cmd = "run",
        data = [top, ":%s/sets.txt" % pm],
        script = "@bazel-orfs//tools/carve:top_level.tcl",
        arguments = top_arguments,
        tags = tags,
        user_arguments = top_level_user_arguments | {
            "CROSSING_SETS": "$(location :%s/sets.txt)" % pm,
            "TOP_DIR": "$(location %s)" % top,
            "TOP_FROM": "grt",
        },
        user_sources = scripts,
    )

    # each set timed in a process of its own
    sets = ":%s_crossing_sets" % pm
    orfs_run(
        name = "%s_crossing_time" % pm,
        src = ":%s_floorplan" % pm,
        out_dir = "%s/time" % pm,
        cmd = "run",
        data = [sets, ":%s/sets.txt" % pm],
        script = "@bazel-orfs//tools/carve:crossing_time_sets.tcl",
        tags = tags,
        user_arguments = {
            "BUDGET_PS": budget_ps,
            "CROSSING_SETS": "$(location :%s/sets.txt)" % pm,
            "SETS_DIR": "$(location %s)" % sets,
        },
        user_sources = scripts,
    )

    # how much earlier each flop launching a crossing over the budget
    # could be clocked, and the hold padding that would take
    # (crossing_launch.tcl): plain timing, run by hand
    orfs_run(
        name = "%s_crossing_launch" % pm,
        src = ":%s_floorplan" % pm,
        out_dir = "%s/launch" % pm,
        cmd = "run",
        data = [sets, ":%s/sets.txt" % pm],
        script = "@bazel-orfs//tools/carve:crossing_time_sets.tcl",
        tags = ["manual"],
        user_arguments = {
            "BUDGET_PS": budget_ps,
            "CROSSING_SETS": "$(location :%s/sets.txt)" % pm,
            "HOLD_TO": "600",
            "SETS_DIR": "$(location %s)" % sets,
        },
        user_sources = scripts | {
            "CROSSING_TIME": ["@bazel-orfs//tools/carve:crossing_launch.tcl"],
        },
    )

    # how much of each set's crossing period the Top could still win, and
    # in which move (crossing_headroom.tcl), each set in an openroad of its
    # own with every thread: run by hand, not on the report's path
    orfs_run(
        name = "%s_crossing_headroom" % pm,
        src = ":%s_floorplan" % pm,
        out_dir = "%s/headroom" % pm,
        cmd = "run",
        data = [sets, ":%s/sets.txt" % pm],
        script = "@bazel-orfs//tools/carve:crossing_headroom_sets.tcl",
        tags = ["manual"],
        user_arguments = {
            "BUDGET_PS": budget_ps,
            "CROSSING_SETS": "$(location :%s/sets.txt)" % pm,
            # skew and VT move the flops of the 200 worst crossing
            # endpoints: skew's hold pass times again after every flop it
            # moves, and every flop of an XSTile set did not end in hours
            "HR_ENDS": "200",
            # skew first, the move a build would act on; the floors after
            "HR_ORDER": "skew wire vt cycles",
            "HR_SETS": headroom_sets,
            # a skew round is a full timing update of the set: an XSTile
            # set's rounds stop after an hour with the best so far
            "HR_SKEW_SECONDS": "3600",
            "HR_SKIP": headroom_skip,
            "SETS_DIR": "$(location %s)" % sets,
        },
        user_sources = scripts | {
            "CROSSING_TIME": ["@bazel-orfs//tools/carve:crossing_headroom.tcl"],
            "HR_TCL": ["@bazel-orfs//tools/odb_debug:headroom.tcl"],
        },
    )

    times = ":%s_crossing_time" % pm
    report = "$(location @bazel-orfs//tools/carve:crossing_report)"
    native.genrule(
        name = "%s_crossings" % pm,
        srcs = [times],
        outs = ["%s/crossings/%s" % (pm, f) for f in ["crossing.txt", "tables.md", "histogram.svg"]],
        cmd = "%s $$(dirname $(location %s/crossings/crossing.txt)) %s $(location %s)" % (report, pm, budget_ps, times),
        tools = ["@bazel-orfs//tools/carve:crossing_report"],
        tags = tags,
    )

    if not whole_check:
        return

    # crossing_cones' flatten mode on the dissolved top level: the
    # boundary logic movable and unrouted, the macros' register-to-register
    # logic and every register fixed (top_flatten_check.tcl)
    orfs_run(
        name = "%s_top_flatten" % pm,
        src = ":%s_floorplan" % pm,
        outs = ["%s/flatten.txt" % pm],
        cmd = "run",
        script = "@bazel-orfs//tools/carve:top_flatten_check.tcl",
        tags = tags,
        user_arguments = {
            "CONE_MACROS": "all",
            "FLATTEN_TXT": "$(location %s/flatten.txt)" % pm,
        },
    )
    sh_test(
        name = "%s_top_flatten_test" % pm,
        srcs = ["@bazel-orfs//tools/carve:top_flatten_check.sh"],
        args = ["$(rootpath :%s/flatten.txt)" % pm],
        data = [":%s/flatten.txt" % pm],
        tags = tags,
    )

    # the method's check, on a design small enough to time whole: the
    # top level timed in one process reports the paths the sets do
    orfs_run(
        name = "%s_crossing_whole" % pm,
        src = ":%s_floorplan" % pm,
        outs = ["%s/whole.txt" % pm],
        cmd = "run",
        data = [top],
        script = "@bazel-orfs//tools/carve:top_level.tcl",
        tags = tags,
        user_arguments = top_level_user_arguments | {
            "BUDGET_PS": budget_ps,
            "CROSSING_TXT": "$(location %s/whole.txt)" % pm,
            "MAX_SKEW_PS": max_skew_ps,
            "TOP_DIR": "$(location %s)" % top,
            "TOP_FROM": "grt",
        },
        user_sources = scripts,
    )

    # the top level taking its macros' boundary logic over (TOP_FLATTEN):
    # placed, repaired and routed again with the crossings whole
    orfs_run(
        name = "%s_top_flat" % pm,
        src = ":%s_floorplan" % pm,
        out_dir = "%s/top_flat" % pm,
        cmd = "run",
        script = "@bazel-orfs//tools/carve:top_level.tcl",
        arguments = top_arguments,
        tags = tags,
        user_arguments = top_level_user_arguments | {
            "MAX_SKEW_PS": max_skew_ps,
            "TOP_FLATTEN": "all",
        } | top_flat_user_arguments,
        user_sources = scripts,
    )
    orfs_run(
        name = "%s_crossing_whole_flat" % pm,
        src = ":%s_floorplan" % pm,
        outs = ["%s/whole_flat.txt" % pm],
        cmd = "run",
        data = [":%s_top_flat" % pm],
        script = "@bazel-orfs//tools/carve:top_level.tcl",
        tags = tags,
        user_arguments = top_level_user_arguments | {
            "BUDGET_PS": budget_ps,
            "CROSSING_TXT": "$(location %s/whole_flat.txt)" % pm,
            "MAX_SKEW_PS": max_skew_ps,
            "TOP_DIR": "$(location :%s_top_flat)" % pm,
            "TOP_FROM": "grt",
        },
        user_sources = scripts,
    )
    if top_flat_check_ps:
        sh_test(
            name = "%s_top_flat_test" % pm,
            srcs = ["@bazel-orfs//tools/carve:top_flat_check.sh"],
            args = [
                "$(rootpath @bazel-orfs//tools/carve:top_flat_check)",
                top_flat_check_ps,
                "$(rootpath :%s/whole.txt)" % pm,
                "$(rootpath :%s/whole_flat.txt)" % pm,
            ],
            data = [
                ":%s/whole.txt" % pm,
                ":%s/whole_flat.txt" % pm,
                "@bazel-orfs//tools/carve:top_flat_check",
            ],
            tags = tags,
        )
    sh_test(
        name = "%s_crossing_test" % pm,
        srcs = ["@bazel-orfs//tools/carve:crossing_check.sh"],
        args = [
            "$(rootpath @bazel-orfs//tools/carve:crossing_report)",
            budget_ps,
            "$(rootpath :%s/whole.txt)" % pm,
            "$(rootpath %s)" % times,
        ],
        data = [
            ":%s/whole.txt" % pm,
            times,
            "@bazel-orfs//tools/carve:crossing_report",
        ],
        tags = tags,
    )

    # the launch-side bound's check: every set's worst launched crossing
    # is the worst crossing the sets' timing reports for it, each room is
    # the smaller of setup and hold, each bound its crossing less its room
    launch = ":%s_crossing_launch" % pm
    sh_test(
        name = "%s_crossing_launch_test" % pm,
        srcs = ["@bazel-orfs//tools/carve:crossing_launch_check.sh"],
        args = [
            "$(rootpath @bazel-orfs//tools/carve:crossing_launch_check)",
            "$(rootpath %s)" % launch,
            "$(rootpath %s)" % times,
        ],
        data = [
            launch,
            times,
            "@bazel-orfs//tools/carve:crossing_launch_check",
        ],
        tags = tags,
    )

    # the headroom's check: every set's period is the worst crossing the
    # sets' timing reports for it, every what-if is undone, and no move
    # reads worse than the design as built
    headroom = ":%s_crossing_headroom" % pm
    sh_test(
        name = "%s_crossing_headroom_test" % pm,
        srcs = ["@bazel-orfs//tools/carve:crossing_headroom_check.sh"],
        args = [
            "$(rootpath @bazel-orfs//tools/carve:crossing_headroom_check)",
            "$(rootpath %s)" % headroom,
            "$(rootpath %s)" % times,
        ],
        data = [
            headroom,
            times,
            "@bazel-orfs//tools/carve:crossing_headroom_check",
        ],
        tags = tags,
    )
