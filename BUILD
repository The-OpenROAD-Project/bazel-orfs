load("//:openroad.bzl", "orfs_make", "orfs_flow", "orfs_run")

# FIXME: this shouldn't be required
exports_files(glob(["*.mk"]))

exports_files(glob(["scripts/mem_dump.*"]))

exports_files(["mock_area.tcl"])

exports_files([
    "orfs",
    "out_script",
    "docker_shell",
])

exports_files(
    glob([
        "test/**/*.sv",
        "test/**/*.sdc",
    ]),
    visibility = [":__subpackages__"],
)

# Config for remote execution
config_setting(
    name = "remote_exec",
    values = {"define": "REMOTE=1"},
    visibility = ["//visibility:public"],
)

orfs_make(
    name = "orfs-make.sh",
    visibility = ["//visibility:public"],
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
}

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "floorplan",
    stage_args = {
        "synth": {
            "SDC_FILE": "$(location :constraints-sram)",
        },
        "floorplan": SRAM_FLOOR_PLACE_ARGUMENTS | {
            "CORE_UTILIZATION": "40",
            "CORE_ASPECT_RATIO": "2",
        },
        "place": SRAM_FLOOR_PLACE_ARGUMENTS | {
            "PLACE_DENSITY": "0.65",
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
        "synth": {"SDC_FILE": "$(location :constraints-sram)"},
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
            "RTLMP_FLOW": "True",
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
    src = ":tag_array_64x184_floorplan",
    outs = [
        "final_clocks.webp.png",
        "final_ir_drop.webp.png",
        "final_placement.webp.png",
        "final_resizer.webp.png",
        "final_routing.webp.png",
        "report.yaml",
    ],
    script = ":report.tcl",
)
