load("//:openroad.bzl", "orfs_flow")

FLOOR_PLACE_ARGUMENTS = {
    "IO_CONSTRAINTS": "$(location //:io)",
}

FAST_SETTINGS = {
    "FILL_CELLS": "",
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
    arguments = FAST_SETTINGS | FLOOR_PLACE_ARGUMENTS | {
        "CORE_AREA": "2 2 18 68",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 20 70",
        "MACRO_PLACE_HALO": "2 2",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "PLACE_DENSITY": "0.30",
        "PLACE_PINS_ARGS": "-annealing",
        "SDC_FILE": "$(location //:test/constraints-top.sdc)",
        "SYNTH_HIERARCHICAL": "1",
    },
    macros = ["//:tag_array_64x184_generate_abstract"],
    stage_sources = {
        "floorplan": ["//:io"],
        "place": ["//:io"],
        "synth": ["//:test/constraints-top.sdc"],
    },
    verilog_files = ["//:test/rtl/L1MetadataArray.sv"],
)

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "place",
    arguments = FAST_SETTINGS | {
        "CORE_ASPECT_RATIO": "2",
        "CORE_UTILIZATION": "4",
        "IO_CONSTRAINTS": "$(location //:io-sram)",
        "PLACE_DENSITY": "0.10",
        "SDC_FILE": "$(location //:constraints-sram)",
    },
    stage_sources = {
        "floorplan": ["//:io-sram"],
        "place": ["//:io-sram"],
        "synth": ["//:constraints-sram"],
    },
    verilog_files = ["//:test/mock/tag_array_64x184.sv"],
)
