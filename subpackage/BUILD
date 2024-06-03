load("//:openroad.bzl", "build_openroad")

build_openroad(
    name = "tag_array_64x184",
    io_constraints = "//:io-sram",
    abstract_stage = "floorplan",
    sdc_constraints = "//:constraints-sram",
    stage_args = {
        "floorplan": [
            "CORE_UTILIZATION=40",
            "CORE_ASPECT_RATIO=2",
        ],
        "place": ["PLACE_DENSITY=0.65"],
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
)

build_openroad(
    name = "L1MetadataArray",
    io_constraints = "//:io",
    macros = ["tag_array_64x184"],
    abstract_stage = "grt",
    sdc_constraints = "//:test/constraints-top.sdc",
    stage_args = {
        "synth": ["SYNTH_HIERARCHICAL=1"],
        "floorplan": [
            "CORE_UTILIZATION=3",
            "RTLMP_FLOW=True",
            "CORE_MARGIN=2",
            "MACRO_PLACE_HALO=30 30",
        ],
        "place": [
            "PLACE_DENSITY=0.20",
            "PLACE_PINS_ARGS=-annealing",
        ],
    },
    verilog_files = ["//:test/rtl/L1MetadataArray.sv"],
)
