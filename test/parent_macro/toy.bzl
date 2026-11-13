"""The miniature parent as a macro."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load("//test/planned_parent:planned.bzl", "BASE_ARGS")
load("//tools/carve:parent_macro.bzl", "parent_macro_flow")

# the register files the parent places as netlists and dissolves itself
FILES = [
    "//test/planned_parent:FileA.regfile",
    "//test/planned_parent:FileB.regfile",
]

# The register file kept as a macro of its own flow, as XSTile's are:
# placed by the plan in the parent, and dissolved by the top level after
# the parent, its cells where its own flow placed them, its registers on
# the top level's clock tree (mini_top_parent_pm_dissolve_nested_test).
FILE_MACRO = "FileC"

# the core's margin inside the plan's outline for the register file, um:
# room for its block grid's ring
FILE_MACRO_MARGIN_UM = 1.0

def _file_macro(plan, module):
    """A register file as a macro of its own flow.

    Its RTL module is the flow's top, generate_ram's netlist inlined there
    with its layout kept (ORFS patch 0172), at the outline the plan left
    for it in the parent, through global route, abstracted there.

    Args:
      plan: the PLAN dict.
      module: the register file's module.

    Returns:
      The abstract's label.
    """
    outline = [n for n in plan["parent"]["netlists"] if n["module"] == module][0]
    w, h, m = outline["w_um"], outline["h_um"], FILE_MACRO_MARGIN_UM
    orfs_flow(
        name = module,
        abstract_stage = "grt",
        arguments = BASE_ARGS | {
            "AUTO_MEMORIES": "1",
            "CORE_AREA": "%s %s %s %s" % (m, m, w - m, h - m),
            "DIE_AREA": "0 0 %s %s" % (w, h),
            # global placement places only what synthesis added around
            # generate_ram's FIRM array: on its own bin grid it diverges
            # (GPL-0305), on four bins a side it does not (as
            # test/planned_parent's FileM)
            "GLOBAL_PLACEMENT_ARGS": "-bin_grid_count 4",
        },
        pdk = "//flow:asap7",
        sources = {
            "AUTO_MEMORIES_REGFILES": ["//test/planned_parent:%s.regfile" % module],
            # a block's grid, so the parent's macro grid connects to it
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
            "SDC_FILE": [":constraints.sdc"],
        },
        tags = ["manual"],
        verilog_files = ["//test/planned_parent:files.sv"],
    )
    return ":%s_generate_abstract" % module

RTL = [
    "//test/planned_parent:files.sv",
    "//test/planned_parent:blocks.sv",
    "//test/planned_parent:top.sv",
]

def toy_parent_macro(plan, blocks):
    """mini_top as a parent macro of blocks, from plan.

    Args:
      plan: the PLAN dict.
      blocks: the blocks, by module.
    """
    file_macro = _file_macro(plan, FILE_MACRO)
    parent_macro_flow(
        plan = plan,
        macros = [file_macro],
        dissolve_nested = {FILE_MACRO: ":%s_grt" % FILE_MACRO},
        # the toy's clock period: every path that fails it
        budget_ps = "1000",
        # one tree, its skew moved by any change of the plan or the tool:
        # 17.9 ps on the first plan, 28.8 and 39.1 on two gcell-aligned
        # ones, 58.2 after the OpenROAD/ORFS bump 3353b055 (each time the
        # worst pair a flop and the parent's register file, latency 200-270
        # ps), 37.4 on the second pass with FileC dissolved by the top
        # level (its worst pair not looked up); a guard against a broken
        # tree, not a QoR target: 80 still stops a tree that misses half
        # the sinks
        max_skew_ps = "80",
        # the method's check: the toy's paths over 150 ps, timed in sets
        # of a few thousand instances, are the paths it reports timed
        # whole (mini_top_parent_pm_crossing_test)
        report_budget_ps = "150",
        plan_budget = "2000",
        whole_check = True,
        # the toy closes at its 1,000 ps and its worst crossing needs about
        # 215 ps, so the second pass's place step is timed at 180 ps, where
        # the crossings fail. One register deep: the paths alone were 212
        # cells, and global placement ended at Nesterov iteration 0 on
        # them (all 212 still moved, so FLW 134 passed it); one deep, 1,035
        # cells (204 registers) with FileC dissolved, it runs 444. The
        # second pass then has 29 pairs over 150 ps against the first's 52,
        # and its worst crossing, the hub's logic between u_BlockA and
        # u_BlockB, 214.6 ps against 215.1: the verdict test asserts the
        # rule's verdict only (mini_top_parent_pm_crossing_verdict_test)
        unfirm_user_arguments = {
            "TOP_CLOCK_PERIOD": "180",
            "TOP_UNFIRM_DEEP": "1",
        },
        # every crossing path over 100 ps in the dataset beside the
        # report, under the budget too (crossing_data.<set>.tsv)
        crossing_data_min_ps = "100",
        name = "mini_top_parent",
        arguments = BASE_ARGS | {
            "AUTO_MEMORIES": "1",
            # the plan places every file as a macro, by its module (<M>.regfile)
            "AUTO_MEMORIES_MACRO_PLACE": " ".join([f.split(":")[-1].removesuffix(".regfile") for f in FILES]),
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
            # as XSTile's parent: the plan places the register file macro
            # FileC where its netlist would go, off the routing tracks'
            # lattice its own flow put its pins on, and pin access finds
            # none on them (DRT-0073 on u_filec/clock)
            "SKIP_PIN_ACCESS": "1",
            # one kept module, its own synthesis partition: the cut-out of
            # the blocks runs in the top's partition alone (evert.tcl)
            "SYNTH_HIERARCHICAL": "1",
            "SYNTH_KEEP_MODULES": "FileM",
        },
        blocks = {
            b: {
                "abstract": ":%s_generate_abstract" % b,
                "grt": ":%s_grt" % b,
            }
            for b in blocks
        },
        # FileM, the register file the plan does not place, is logic here,
        # a kept module of its own (SYNTH_KEEP_MODULES above)
        place_macros = "//test/planned_parent:plan/place_macros.tcl",
        plan_pins = {b: "//test/planned_parent:plan/%s_pins.tcl" % b for b in blocks},
        sources = {
            "AUTO_MEMORIES_REGFILES": FILES,
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl"],
            "SDC_FILE": [":constraints.sdc"],
        },
        top = "mini_top",
        top_arguments = {
            "MAX_ROUTING_LAYER": "M9",
            "MIN_ROUTING_LAYER": "M2",
        },
        # as the parent, the largest of the macros: its guides end at pin
        # shape centres. XSTile skips it too, so no target runs
        # top_level.tcl's pin_access branch
        top_level_arguments = {"SKIP_PIN_ACCESS": "1"},
        top_sources = {"SDC_FILE": [":constraints.sdc"]},
        verilog_files = RTL,
    )
