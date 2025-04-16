load("//:openroad.bzl", "orfs_flow")

FLOOR_PLACE_ARGUMENTS = {
    "IO_CONSTRAINTS": "$(location //:io)",
}

FAST_SETTINGS = {
    "FILL_CELLS": "",
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_REPORT_METRICS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_INCREMENTAL_REPAIR": "1",
    "TAPCELL_TCL": "",
    "GND_NETS_VOLTAGES": "",
    "PWR_NETS_VOLTAGES": "",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_TIMING_DRIVEN": "0",
}

orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "place",
    arguments = FAST_SETTINGS | FLOOR_PLACE_ARGUMENTS | {
        "SDC_FILE": "$(location //:test/constraints-top.sdc)",
        "SYNTH_HIERARCHICAL": "1",
        "CORE_UTILIZATION": "3",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "30 30",
        "PLACE_DENSITY": "0.20",
        "PLACE_PINS_ARGS": "-annealing",
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
        "SDC_FILE": "$(location //:constraints-sram)",
        "CORE_UTILIZATION": "4",
        "CORE_ASPECT_RATIO": "2",
        "PLACE_DENSITY": "0.10",
        "IO_CONSTRAINTS": "$(location //:io-sram)",
    },
    stage_sources = {
        "synth": ["//:constraints-sram"],
        "floorplan": ["//:io-sram"],
        "place": ["//:io-sram"],
    },
    verilog_files = ["//:test/mock/tag_array_64x184.sv"],
)
