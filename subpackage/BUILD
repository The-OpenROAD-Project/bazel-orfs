load("//:openroad.bzl", "build_openroad")

build_openroad(
    name = "L1MetadataArray",
    io_constraints = "//:io",
    macros = ["//:tag_array_64x184"],
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
