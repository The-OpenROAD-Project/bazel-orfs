load("//:openroad.bzl", "orfs_flow")

FLOOR_PLACE_ARGUMENTS = {
    "IO_CONSTRAINTS": "$(location //:io)",
}

# faster build
FAST_ARGUMENTS = {
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_REPORT_METRICS": "1",
}

orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "cts",
    arguments = FAST_ARGUMENTS,
    macros = ["//:tag_array_64x184_generate_abstract"],
    stage_arguments = {
        "synth": {
            "SDC_FILE": "$(location //:test/constraints-top.sdc)",
            "SYNTH_HIERARCHICAL": "1",
        },
        "floorplan": FLOOR_PLACE_ARGUMENTS | {
            "CORE_UTILIZATION": "3",
            "RTLMP_FLOW": "1",
            "CORE_MARGIN": "2",
            "MACRO_PLACE_HALO": "30 30",
        },
        "place": FLOOR_PLACE_ARGUMENTS | {
            "PLACE_DENSITY": "0.20",
            "PLACE_PINS_ARGS": "-annealing",
        },
    },
    stage_sources = {
        "floorplan": ["//:io"],
        "place": ["//:io"],
        "synth": ["//:test/constraints-top.sdc"],
    },
    verilog_files = ["//:test/rtl/L1MetadataArray.sv"],
)

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "floorplan",
    arguments = FAST_ARGUMENTS,
    stage_arguments = {
        "synth": {
            "SDC_FILE": "$(location //:constraints-sram)",
        },
        "floorplan": {
            "CORE_UTILIZATION": "10",
            "CORE_ASPECT_RATIO": "2",
            "IO_CONSTRAINTS": "$(location //:io-sram)",
        },
        "place": {
            "PLACE_DENSITY": "0.65",
            "IO_CONSTRAINTS": "$(location //:io-sram)",
        },
    },
    stage_sources = {
        "synth": ["//:constraints-sram"],
        "floorplan": ["//:io-sram"],
        "place": ["//:io-sram"],
    },
    verilog_files = ["//:test/mock/tag_array_64x184.sv"],
)
