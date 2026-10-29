"""The miniature parent as a macro."""

load("//test/planned_parent:planned.bzl", "BASE_ARGS")
load("//tools/carve:parent_macro.bzl", "parent_macro_flow")

FILES = [
    "//test/planned_parent:FileA.regfile",
    "//test/planned_parent:FileB.regfile",
    "//test/planned_parent:FileC.regfile",
]

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
    parent_macro_flow(
        plan = plan,
        # the toy's clock period: every path that fails it
        budget_ps = "1000",
        # one tree, its skew moved by any change of the plan: 17.9 ps on the
        # first plan, 28.8 and 39.1 on two gcell-aligned ones (the worst
        # pair a flop and the parent's register file, latency 220-270 ps);
        # 50 still stops a tree that misses half the sinks
        max_skew_ps = "50",
        # the method's check: the toy's paths over 150 ps, timed in sets
        # of a few thousand instances, are the paths it reports timed
        # whole (mini_top_parent_pm_crossing_test)
        report_budget_ps = "150",
        plan_budget = "2000",
        whole_check = True,
        name = "mini_top_parent",
        arguments = BASE_ARGS | {
            "AUTO_MEMORIES": "1",
            # the plan places every file as a macro, by its module (<M>.regfile)
            "AUTO_MEMORIES_MACRO_PLACE": " ".join([f.split(":")[-1].removesuffix(".regfile") for f in FILES]),
            "RTLMP_MIN_CHANNEL_SIZE": "4 4",
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
        top_sources = {"SDC_FILE": [":constraints.sdc"]},
        verilog_files = RTL,
    )
