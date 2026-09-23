"""The miniature planned parent's flows: four blocks abstracted at place, the parent through global route."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("//test/grt_scaling:arms.bzl", "TURNAROUND_ARGS")
load(":plan/plan.bzl", "PLAN")

# asap7, the pin layers of the study, the margin knobs of the first flow
BASE_ARGS = TURNAROUND_ARGS | {
    "IO_PLACER_H": "M2 M4",
    "IO_PLACER_V": "M3 M5",
    "MAX_ROUTING_LAYER": "M7",
    "MIN_ROUTING_LAYER": "M2",
    "PLACE_DENSITY": "0.5",
    "PLACE_PINS_ARGS": "-annealing",
    "SYNTH_HDL_FRONTEND": "slang",
}

def mini_planned_flow(rtl, files):
    """The blocks named in PLAN, each at its planned outline with its pins on
    the planned side, abstracted at place; the parent at the planned die,
    the blocks placed by the plan, the files as placed netlists, to grt.

    Args:
      rtl: the genrule that writes blocks.sv, files.sv and top.sv.
      files: the register-file spec labels (mode netlist).
    """
    for block in sorted(PLAN["macros"]):
        entry = PLAN["macros"][block]
        orfs_flow(
            name = block,
            abstract_stage = "place",
            arguments = BASE_ARGS | {
                "AUTO_MEMORIES": "0",
                "CORE_AREA": entry["CORE_AREA"],
                "DIE_AREA": entry["DIE_AREA"],
            },
            pdk = "//flow:asap7",
            sources = {
                "IO_CONSTRAINTS": [":plan/%s_pins.tcl" % block],
                "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCK_grid_strategy.tcl"],
                "SDC_FILE": [":constraints.sdc"],
            },
            verilog_files = [":blocks.sv"],
        )
    parent_args = BASE_ARGS | {
        "AUTO_MEMORIES": "1",
        "CORE_AREA": PLAN["parent"]["CORE_AREA"],
        "DIE_AREA": PLAN["parent"]["DIE_AREA"],
        "MACRO_PLACE_HALO": "2 2",
    }
    parent_sources = {
        "MACRO_PLACEMENT_TCL": [":plan/place_macros.tcl"],
        "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl"],
        "SDC_FILE": [":constraints.sdc"],
        "STRUCTURED_MEMORIES": files,
        "STRUCTURED_PLACEMENT": [":plan/netlists.txt"],
    }
    parent_macros = [":%s_generate_abstract" % b for b in sorted(PLAN["macros"])]
    orfs_flow(
        name = "mini_top",
        arguments = parent_args,
        last_stage = "grt",
        macros = parent_macros,
        pdk = "//flow:asap7",
        sources = parent_sources,
        verilog_files = [":files.sv", ":top.sv"],
    )

    # The same parent's CTS without insertion-delay balancing, on the base
    # variant's placement: the pair cts_delay_buffers_test reads. ORFS's
    # cts_args are -sink_clustering_enable -repair_clock_nets; CTS_ARGS
    # replaces them wholesale, so both are repeated here.
    orfs_flow(
        name = "mini_top",
        arguments = parent_args | {
            "CTS_ARGS": "-sink_clustering_enable -repair_clock_nets -no_insertion_delay",
        },
        last_stage = "cts",
        macros = parent_macros,
        pdk = "//flow:asap7",
        previous_stage = {"cts": ":mini_top_place"},
        sources = parent_sources,
        variant = "nid",
        verilog_files = [":files.sv", ":top.sv"],
    )
    for tag, src in (("base", ":mini_top_cts"), ("nid", ":mini_top_nid_cts")):
        orfs_run(
            name = "cts_buffers_" + tag,
            src = src,
            outs = ["cts_buffers_%s.json" % tag],
            arguments = parent_args,
            script = ":cts_buffers.tcl",
            sources = parent_sources,
            src_logs = True,
            user_arguments = {
                "OUTPUT_JSON": "$(location cts_buffers_%s.json)" % tag,
            },
            variant = tag,
        )

    # The route-0 gate on the miniature: a zero-iteration global route on
    # its CTS checkpoint, the congestion totals as JSON and the congested
    # regions as the router reports them, for the wall the parent met in
    # the gap between two blocks (inventory entry 13).
    orfs_run(
        name = "route0_mini",
        src = ":mini_top_cts",
        outs = [
            "route0_mini.json",
            "route0_mini_congestion.txt",
        ],
        arguments = parent_args,
        script = "//test/macro_select:route0.tcl",
        sources = parent_sources,
        user_arguments = {
            "CONGESTION_REPORT": "$(location route0_mini_congestion.txt)",
            "OUTPUT_JSON": "$(location route0_mini.json)",
        },
    )
