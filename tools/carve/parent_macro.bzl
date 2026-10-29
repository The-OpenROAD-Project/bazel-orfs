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
        arguments = arguments | {
            "CORE_AREA": plan["parent"]["CORE_AREA"],
            "DIE_AREA": plan["parent"]["DIE_AREA"],
            "OPENROAD_HIERARCHICAL": "0",
            # the first flush through grt is for turnaround: XSTile_parent's
            # CTS setup repair ground for over an hour at WNS -437 ps
            # without moving it, on the 4771 x 2064 um die
            "SKIP_CTS_REPAIR_TIMING": "1",
            "SKIP_INCREMENTAL_REPAIR": "1",
            "SYNTH_BLACKBOXES": " ".join(names),
        },
        last_stage = "grt",
        macros = macros,
        pdk = pdk,
        sources = parent_sources,
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
        tags = tags,
    )

def _top_level(pm, budget_ps, max_skew_ps, plan_budget, top_level_arguments, top_level_user_arguments, whole_check, tags):
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
        # (patch 0159)
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
