load("//:eqy.bzl", "eqy_test")
load("//:openroad.bzl", "orfs_flow", "orfs_run")

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

SRAM_ARGUMENTS = {
    "SDC_FILE": "$(location :constraints-sram)",
    "IO_CONSTRAINTS": "$(location :io-sram)",
    "PLACE_PINS_ARGS": "-min_distance 2 -min_distance_in_tracks",
    "PLACE_DENSITY": "0.42",
    "REMOVE_ABC_BUFFERS": "1",
    # faster build
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_REPORT_METRICS": "1",
}

BLOCK_FLOORPLAN = {
    "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    # repair_timing runs for hours in floorplan
    "REMOVE_ABC_BUFFERS": "1",
}

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "cts",
    args = SRAM_ARGUMENTS | {
        "CORE_UTILIZATION": "40",
        "CORE_ASPECT_RATIO": "2",
        "SKIP_REPORT_METRICS": "1",
    },
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)

LB_ARGS = SRAM_ARGUMENTS | {
    "CORE_UTILIZATION": "40",
    "CORE_ASPECT_RATIO": "2",
    "PLACE_DENSITY": "0.65"
}

LB_STAGE_SOURCES = {
    "synth": [":constraints-sram"],
    "floorplan": [":io-sram"],
    "place": [":io-sram"],
}

LB_VERILOG_FILES = ["test/mock/lb_32x128.sv"]

orfs_flow(
    name = "lb_32x128",
    abstract_stage = "floorplan",
    mock_area = 1.0,
    args = LB_ARGS,
    stage_sources = LB_STAGE_SOURCES,
    verilog_files = LB_VERILOG_FILES,
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "place",
    args = LB_ARGS,
    stage_sources = LB_STAGE_SOURCES,
    variant = "test",
    verilog_files = LB_VERILOG_FILES,
)

orfs_flow(
    name = "L1MetadataArray",
    abstract_stage = "cts",
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
        "final": {
            "GND_NETS_VOLTAGES": "",
            "PWR_NETS_VOLTAGES": "",
        },
    },
    stage_sources = {
        "synth": [":test/constraints-top.sdc"],
    },
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)

orfs_run(
    name = "tag_array_64x184_report",
    src = ":tag_array_64x184_place",
    outs = [
        "report.yaml",
    ],
    script = ":report.tcl",
)

orfs_flow(
    name = "Mul",
    abstract_stage = "synth",
    stage_args = {
        "synth": {
            "SDC_FILE": "$(location :test/constraints-top.sdc)",
        },
    },
    stage_sources = {
        "synth": [":test/constraints-top.sdc"],
    },
    verilog_files = ["test/rtl/Mul.sv"],
)

filegroup(
    name = "Mul_synth_verilog",
    srcs = [
        "Mul_synth",
    ],
    output_group = "1_synth.v",
)

eqy_test(
    name = "Mul_synth_eqy",
    depth = 2,
    gate_verilog_files = [
        ":Mul_synth_verilog",
        "@docker_orfs//:OpenROAD-flow-scripts/flow/platforms/asap7/work_around_yosys/asap7sc7p5t_AO_RVT_TT_201020.v",
        "@docker_orfs//:OpenROAD-flow-scripts/flow/platforms/asap7/work_around_yosys/asap7sc7p5t_INVBUF_RVT_TT_201020.v",
        "@docker_orfs//:OpenROAD-flow-scripts/flow/platforms/asap7/work_around_yosys/asap7sc7p5t_OA_RVT_TT_201020.v",
        "@docker_orfs//:OpenROAD-flow-scripts/flow/platforms/asap7/work_around_yosys/asap7sc7p5t_SIMPLE_RVT_TT_201020.v",
    ],
    gold_verilog_files = [
        "test/rtl/Mul.sv",
    ],
    module_top = "Mul",
)

orfs_flow(
    name = "data_2048x8",
    abstract_stage = "cts",
    args = SRAM_ARGUMENTS,
    stage_args = {
        "synth": {"SYNTH_MEMORY_MAX_BITS": "16384"},
        "floorplan": BLOCK_FLOORPLAN | {
            "CORE_UTILIZATION": "40",
            "CORE_ASPECT_RATIO": "2",
        },
        "place": {
            "PLACE_DENSITY": "0.65",
            "GPL_TIMING_DRIVEN": "0",
        },
        "cts": {
            "SKIP_REPORT_METRICS": "1",
        },
    },
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = [
        "test/rtl/data_2048x8.sv"
    ],
)

orfs_flow(
    name = "regfile_128x65",
    abstract_stage = "cts",
    args = SRAM_ARGUMENTS,
    stage_args = {
        "floorplan": BLOCK_FLOORPLAN | {
            "DIE_AREA": "0 0 400 400",
            "CORE_AREA": "2 2 298 298",
            "IO_CONSTRAINTS": "$(location :io-sram)",
        },
        "place": {
            "PLACE_DENSITY": "0.3",
            "IO_CONSTRAINTS": "$(location :io-sram)",
        },
    },
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = [
        "test/rtl/regfile_128x65.sv"
    ],
)
