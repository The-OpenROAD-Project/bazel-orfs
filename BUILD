load("//:openroad.bzl", "orfs_flow", "orfs_run")

# FIXME: this shouldn't be required
exports_files(glob(["*.mk"]))

exports_files(glob(["scripts/mem_dump.*"]))

exports_files(["mock_area.tcl"])

exports_files(
    glob([
        "test/**/*.sv",
        "test/**/*.sdc",
    ]),
    visibility = [":__subpackages__"],
)

filegroup(
    name = "io-sram",
    srcs = [
        ":test/io-sram.tcl",
    ],
    data = [
        ":test/util.tcl",
    ],
    visibility = [":__subpackages__"],
)

filegroup(
    name = "io",
    srcs = [
        ":test/io.tcl",
    ],
    data = [
        ":test/util.tcl",
    ],
    visibility = [":__subpackages__"],
)

filegroup(
    name = "constraints-sram",
    srcs = [
        ":test/constraints-sram.sdc",
    ],
    data = [
        ":test/util.tcl",
    ],
    visibility = [":__subpackages__"],
)

SRAM_FLOOR_PLACE_ARGUMENTS = {
    "IO_CONSTRAINTS": "$(location :io-sram)",
    "PLACE_PINS_ARGS": "-min_distance 2 -min_distance_in_tracks",
}

SRAM_SYNTH_ARGUMENTS = {
    "SDC_FILE": "$(location :constraints-sram)",
}

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "route",
    stage_args = {
        "synth": SRAM_SYNTH_ARGUMENTS,
        "floorplan": SRAM_FLOOR_PLACE_ARGUMENTS | {
            "CORE_UTILIZATION": "40",
            "CORE_ASPECT_RATIO": "2",
            "SKIP_REPORT_METRICS": "1"
        },
        "place": SRAM_FLOOR_PLACE_ARGUMENTS | {
            "PLACE_DENSITY": "0.40",
            "SKIP_REPORT_METRICS": "1",
        },
        "cts": {
            "SKIP_REPORT_METRICS": "1",
        },
        "grt": {
            "SKIP_REPORT_METRICS": "1",
        },
        "route": {
            "SKIP_REPORT_METRICS": "1",
        },
        "final": {
            "SKIP_REPORT_METRICS": "1",
        },
    },
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)

orfs_flow(
    name = "lb_32x128",
    abstract_stage = "floorplan",
    stage_args = {
        "synth": SRAM_SYNTH_ARGUMENTS,
        "floorplan": SRAM_FLOOR_PLACE_ARGUMENTS | {
            "CORE_UTILIZATION": "40",
            "CORE_ASPECT_RATIO": "2",
        },
        "place": SRAM_FLOOR_PLACE_ARGUMENTS | {"PLACE_DENSITY": "0.65"},
    },
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = ["test/rtl/lb_32x128.sv"],
)

orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "route",
    macros = ["tag_array_64x184_generate_abstract"],
    stage_args = {
        "synth": {
            "SDC_FILE": "$(location :test/constraints-top.sdc)",
            "SYNTH_HIERARCHICAL": "1",
        },
        "floorplan": {
            "CORE_UTILIZATION": "3",
            "RTLMP_FLOW": "1",
            "CORE_MARGIN": "2",
            "MACRO_PLACE_HALO": "30 30",
        },
        "place": {
            "PLACE_DENSITY": "0.20",
            "PLACE_PINS_ARGS": "-annealing",
        },
    },
    stage_sources = {
        "synth": [":test/constraints-top.sdc"],
    },
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)

orfs_run(
    name = "tag_array_64x184_report",
    src = ":tag_array_64x184_route",
    outs = [
        "report.yaml",
    ],
    script = ":report.tcl",
)
