load("//:openroad.bzl", "orfs_flow")

FAST_SETTINGS = {
    "FILL_CELLS": "",
    "GLOBAL_PLACEMENT_ARGS": "-overflow 0.2",
    "GND_NETS_VOLTAGES": "",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_TIMING_DRIVEN": "0",
    "PWR_NETS_VOLTAGES": "",
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_INCREMENTAL_REPAIR": "1",
    "SKIP_REPORT_METRICS": "1",
    "TAPCELL_TCL": "",
}

orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "place",
    arguments = FAST_SETTINGS | {
        "CORE_AREA": "2 2 20 80",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 22 82",
        "MACRO_PLACE_HALO": "2 2",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "PLACE_DENSITY": "0.40",
        "PLACE_PINS_ARGS": "-annealing",
        "SYNTH_HIERARCHICAL": "1",
    },
    macros = ["//test:tag_array_64x184_generate_abstract"],
    sources = {
        "IO_CONSTRAINTS": ["//test:io"],
        "SDC_FILE": ["//test:constraints-top.sdc"],
    },
    verilog_files = ["//test:rtl/L1MetadataArray.sv"],
)

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "place",
    arguments = FAST_SETTINGS | {
        "CORE_AREA": "1.026 1.080 7.560 50.220",
        "DIE_AREA": "0 0 8.586 51.300",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
        "PLACE_DENSITY": "0.65",
        "PLACE_PINS_ARGS": "-min_distance 2 -min_distance_in_tracks",
    },
    sources = {
        "IO_CONSTRAINTS": ["//test:io-sram"],
        "SDC_FILE": ["//test:constraints-sram"],
    },
    verilog_files = ["//test:mock/tag_array_64x184.sv"],
)
