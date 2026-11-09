"""The miniature parent as a macro."""

load("@bazel-orfs//:openroad.bzl", "orfs_run")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
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

# The toy's SDC is its clock alone; boundary budgets for the ledger to
# count pins over, set where the parent has pins over each of them.
LEDGER = {
    "LEDGER_IN2OUT_PS": "100",
    "LEDGER_IN2REG_PS": "300",
    "LEDGER_REG2OUT_PS": "600",
    "LEDGER_SKEW": "1",
}

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
        # one tree, its skew moved by any change of the plan or the tool:
        # 17.9 ps on the first plan, 28.8 and 39.1 on two gcell-aligned
        # ones, 58.2 after the OpenROAD/ORFS bump 3353b055 (each time the
        # worst pair a flop and the parent's register file, latency 200-270
        # ps); a guard against a broken tree, not a QoR target: 80 still
        # stops a tree that misses half the sinks
        max_skew_ps = "80",
        # the method's check: the toy's paths over 150 ps, timed in sets
        # of a few thousand instances, are the paths it reports timed
        # whole (mini_top_parent_pm_crossing_test)
        report_budget_ps = "150",
        plan_budget = "2000",
        whole_check = True,
        # the toy closes at its 1,000 ps; its worst crossing needs 201 ps,
        # so the top level that takes the boundary logic over repairs to
        # 180 ps, where its crossings fail and repair has work to do
        top_flat_user_arguments = {"TOP_CLOCK_PERIOD": "180"},
        # 201.4 ps as built, 187.5 flattened (mini_top_parent_pm_top_flat_test)
        top_flat_check_ps = "190",
        # the crossings again without a top level, each part's halves
        # summed along each crossing net, and checked against the top
        # level's own paths through each (mini_top_parent_pm_ledger_test)
        ledger = True,
        ledger_user_arguments = LEDGER,
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

    # A part's own boundary constraints change none of its halves: the
    # parent's, which has every kind, read again with the platform's
    # set_max_delay budgets on top of the toy's clock, as a real part's
    # SDC has them.
    orfs_run(
        name = "mini_top_parent_pm_mini_top_ledger_budgets",
        src = ":mini_top_parent_grt",
        outs = ["mini_top_parent_pm/ledger/budgets/mini_top.txt"],
        cmd = "run",
        script = "//tools/carve:crossing_ledger.tcl",
        tags = ["manual"],
        user_arguments = LEDGER | {
            "LEDGER_OUT": "$(location mini_top_parent_pm/ledger/budgets/mini_top.txt)",
        },
        user_sources = {
            "HR_TCL": ["//tools/odb_debug:headroom.tcl"],
            "LEDGER_EXTRA_SDC": [":ledger_budgets.sdc"],
        },
    )
    sh_test(
        name = "mini_top_parent_pm_ledger_budgets_test",
        srcs = ["//tools/carve:crossing_ledger_check.sh"],
        args = [
            "$(rootpath //tools/carve:crossing_ledger_check)",
            "same",
            "$(rootpath :mini_top_parent_pm/ledger/parts/mini_top.txt)",
            "$(rootpath :mini_top_parent_pm/ledger/budgets/mini_top.txt)",
        ],
        data = [
            ":mini_top_parent_pm/ledger/budgets/mini_top.txt",
            ":mini_top_parent_pm/ledger/parts/mini_top.txt",
            "//tools/carve:crossing_ledger_check",
        ],
        tags = ["manual"],
    )
