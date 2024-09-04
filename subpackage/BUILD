load("//:openroad.bzl", "orfs_flow")

FLOOR_PLACE_ARGUMENTS = {
    "IO_CONSTRAINTS": "$(location //:io)",
}

orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "route",
    macros = ["//:tag_array_64x184_generate_abstract"],
    stage_args = {
        "synth": {
            "SDC_FILE": "$(location //:test/constraints-top.sdc)",
            "SYNTH_HIERARCHICAL": "1",
        },
        "floorplan": FLOOR_PLACE_ARGUMENTS | {
            "CORE_UTILIZATION": "3",
            "RTLMP_FLOW": "True",
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
    common_args = {
        "GENERATE_ARTIFACTS_ON_FAILURE": "1",
    },
)
