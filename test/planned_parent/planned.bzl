"""The miniature planned parent's flows: four blocks abstracted at place, the parent through global route."""

load("@bazel-orfs//:openroad.bzl", "orfs_flow")
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
    orfs_flow(
        name = "mini_top",
        arguments = BASE_ARGS | {
            "AUTO_MEMORIES": "1",
            "CORE_AREA": PLAN["parent"]["CORE_AREA"],
            "DIE_AREA": PLAN["parent"]["DIE_AREA"],
            "MACRO_PLACE_HALO": "2 2",
        },
        last_stage = "grt",
        macros = [":%s_generate_abstract" % b for b in sorted(PLAN["macros"])],
        pdk = "//flow:asap7",
        sources = {
            "MACRO_PLACEMENT_TCL": [":plan/place_macros.tcl"],
            "PDN_TCL": ["//flow:platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl"],
            "SDC_FILE": [":constraints.sdc"],
            "STRUCTURED_MEMORIES": files,
            "STRUCTURED_PLACEMENT": [":plan/netlists.txt"],
        },
        verilog_files = [":files.sv", ":top.sv"],
    )
