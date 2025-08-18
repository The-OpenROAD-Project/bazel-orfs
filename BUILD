load("@aspect_rules_js//js:defs.bzl", "js_binary")

# Unused in CI
#
# load("@bazel-orfs//tools/pin:pin.bzl", "pin_data")
load("@bazel-orfs//toolchains/scala:chisel.bzl", "chisel_library")
load("@bazel-orfs//toolchains/scala:scala_bloop.bzl", "scala_bloop")
load("@bazel_orfs_rules_python//python:defs.bzl", "py_binary")
load("@bazel_orfs_rules_python//python:pip.bzl", "compile_pip_requirements")
load("@npm//:defs.bzl", "npm_link_all_packages")

# Reenable when we add test back in
# load("//:eqy.bzl", "eqy_test")
load("//:netlistsvg.bzl", "netlistsvg")
load("//:openroad.bzl", "get_stage_args", "orfs_floorplan", "orfs_flow", "orfs_macro", "orfs_run", "orfs_synth")
load("//:ppa.bzl", "orfs_ppa")
load("//:sweep.bzl", "orfs_sweep")
load("//:yosys.bzl", "yosys")

exports_files([
    "mock_area.tcl",
    "oss_cad_suite.BUILD.bazel",
])

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

SRAM_ARGUMENTS = FAST_SETTINGS | {
    "SDC_FILE": "$(location :constraints-sram)",
    "IO_CONSTRAINTS": "$(location :io-sram)",
    "PLACE_PINS_ARGS": "-min_distance 2 -min_distance_in_tracks",
    "PLACE_DENSITY": "0.42",
}

BLOCK_FLOORPLAN = {
    "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    # repair_timing runs for hours in floorplan
    "REMOVE_ABC_BUFFERS": "1",
}

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "cts",
    arguments = SRAM_ARGUMENTS | {
        "CORE_UTILIZATION": "2",
        "CORE_ASPECT_RATIO": "2",
        "SKIP_REPORT_METRICS": "1",
    },
    # FIXME reenable after https://github.com/The-OpenROAD-Project/OpenROAD/issues/7745 is fixed
    # mock_area = 0.8,
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = [":__subpackages__"],
)

LB_ARGS = SRAM_ARGUMENTS | {
    "CORE_UTILIZATION": "15",
    "CORE_ASPECT_RATIO": "2",
    "PLACE_DENSITY": "0.20",
    "PLACE_PINS_ARGS": "-min_distance 1 -min_distance_in_tracks",
}

LB_STAGE_SOURCES = {
    "synth": [":constraints-sram"],
    "floorplan": [":io-sram"],
    "place": [":io-sram"],
}

LB_VERILOG_FILES = ["test/mock/lb_32x128.sv"]

# Test a full abstract, all stages, so leave abstract_stage unset to default value(final)
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    mock_area = 0.7,
    stage_sources = LB_STAGE_SOURCES,
    verilog_files = LB_VERILOG_FILES,
)

# buildifier: disable=duplicated-name
orfs_floorplan(
    name = "lb_32x128_shared_synth_floorplan",
    src = ":lb_32x128_synth",
    # Make sure we're not passing in any non-floorplan arguments
    arguments = get_stage_args("floorplan", {}, LB_ARGS, {}),
    data = LB_STAGE_SOURCES["floorplan"],
    variant = "blah",
)

orfs_flow(
    name = "lb_32x128_top",
    abstract_stage = "place",
    arguments = LB_ARGS | {
        "CORE_UTILIZATION": "1",
        "PLACE_DENSITY": "0.10",

        # Skip power checks to silence error and speed up build
        "PWR_NETS_VOLTAGES": "",
        "GND_NETS_VOLTAGES": "",
        "GDS_ALLOW_EMPTY": "lb_32x128",
    },
    macros = ["lb_32x128_generate_abstract"],
    stage_sources = LB_STAGE_SOURCES,
    verilog_files = ["test/rtl/lb_32x128_top.v"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "place",
    arguments = LB_ARGS,
    stage_sources = LB_STAGE_SOURCES,
    variant = "test",
    verilog_files = LB_VERILOG_FILES,
)

orfs_run(
    name = "cell_count",
    src = ":lb_32x128_floorplan",
    outs = [
        "test.txt",
    ],
    extra_args = "> $WORK_HOME/test.txt",
    script = ":cell_count.tcl",
)

filegroup(
    name = "tag_array_64x184_libs",
    srcs = ["tag_array_64x184_generate_abstract"],
    output_group = "tag_array_64x184_typ.lib",
)

filegroup(
    name = "tag_array_64x184_lefs",
    srcs = ["tag_array_64x184_generate_abstract"],
    output_group = "tag_array_64x184.lef",
)

orfs_macro(
    name = "amalgam",
    lef = "tag_array_64x184_lefs",
    lib = "tag_array_64x184_libs",
    module_top = "tag_array_64x184",
)

# Run one macro through all stages
orfs_sweep(
    name = "L1MetadataArray",
    arguments = FAST_SETTINGS |
                {
                    "SYNTH_HIERARCHICAL": "1",
                    "CORE_UTILIZATION": "3",
                    "CORE_MARGIN": "2",
                    "MACRO_PLACE_HALO": "30 30",
                    "PLACE_DENSITY": "0.05",
                    "GDS_ALLOW_EMPTY": "tag_array_64x184",
                },
    sweep = {
        "base": {
            "macros": ["tag_array_64x184_generate_abstract"],
            "sources": {
                "SDC_FILE": [":test/constraints-top.sdc"],
            },
        },
        "1": {
            "macros": ["amalgam"],
            "sources": {
                "SDC_FILE": [":test/constraints-top.sdc"],
            },
        },
    },
    verilog_files = ["test/rtl/L1MetadataArray.sv"],
)

orfs_run(
    name = "check_mock_area",
    src = ":L1MetadataArray_floorplan",
    outs = [
        "area_ok.txt",
    ],
    script = ":check_mock_area.tcl",
)

orfs_run(
    name = "tag_array_64x184_report",
    src = ":tag_array_64x184_place",
    outs = [
        "report.yaml",
    ],
    script = ":report.tcl",
)

orfs_synth(
    name = "Mul_synth",
    arguments = {
        "SDC_FILE": "$(location :test/constraints-combinational.sdc)",
    },
    data = [":test/constraints-combinational.sdc"],
    module_top = "Mul",
    verilog_files = ["test/rtl/Mul.sv"],
)

filegroup(
    name = "Mul_synth_verilog",
    srcs = [
        "Mul_synth",
    ],
    output_group = "1_synth.v",
)

# FIXME update to using .lib cells after
# https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/pull/3377
#
# Yosys no longer has this multiply bug that we're testing for.
#
# eqy_test(
#     name = "Mul_synth_eqy",
#     depth = 2,
#     gate_verilog_files = [
#         ":Mul_synth_verilog",
#     ],
#     gold_verilog_files = [
#         "test/rtl/Mul.sv",
#     ],
#     module_top = "Mul",
# )

# Need full flow to test final gatelist extraction
orfs_flow(
    name = "regfile_128x65",
    arguments = SRAM_ARGUMENTS | BLOCK_FLOORPLAN | {
        "DIE_AREA": "0 0 400 400",
        "CORE_AREA": "2 2 298 298",
        "IO_CONSTRAINTS": "$(location :io-sram)",
        "PLACE_DENSITY": "0.10",
    },
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    verilog_files = [
        "test/rtl/regfile_128x65.sv",
    ],
)

# buildifier: disable=duplicated-name
orfs_sweep(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    stage = "cts",
    stage_sources = {
        "synth": [":constraints-sram"],
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
    },
    sweep = {
        "1": {
            "arguments": {
                "PLACE_DENSITY": "0.20",
            },
            "previous_stage": {"floorplan": "lb_32x128_synth"},
        },
        "2": {
            "arguments": {
                "PLACE_DENSITY": "0.21",
            },
            "previous_stage": {"place": "lb_32x128_floorplan"},
        },
        "3": {
            "arguments": {
                "PLACE_DENSITY": "0.22",
            },
            "previous_stage": {"cts": "lb_32x128_place"},
        },
    },
    verilog_files = ["test/mock/lb_32x128.sv"],
)

exports_files(
    [
        "sweep-wns.tcl",
        "wns_report.py",
        "power.tcl",
        "open_plots.sh",
    ],
)

orfs_run(
    name = "sta",
    src = ":lb_32x128_floorplan",
    outs = [
        "units.txt",
    ],
    arguments = {
        "OPENROAD_EXE": "$$OPENSTA_EXE",
        "OUTPUT": "$(location units.txt)",
    },
    script = ":units.tcl",
)

compile_pip_requirements(
    name = "requirements",
    src = "requirements.in",
    python_version = "3.13",
    requirements_txt = "requirements_lock_3_13.txt",
)

py_binary(
    name = "plot_repair",
    srcs = [
        "plot-retiming.py",
    ],
    main = "plot-retiming.py",
    visibility = ["//visibility:public"],
    deps = ["@bazel-orfs-pip//matplotlib"],
)

filegroup(
    name = "gatelist",
    srcs = [
        "lb_32x128_final",
        "regfile_128x65_final",
    ],
    output_group = "6_final.v",
)

filegroup(
    name = "spef",
    srcs = [
        "lb_32x128_final",
        "regfile_128x65_final",
    ],
    output_group = "6_final.spef",
)

# gate netlists can be build by e.g. Verilator, mock
# usage of the gate netlists here to demonstrate the
# usecase
genrule(
    name = "gatelist_wc",
    srcs = [
        ":gatelist",
        ":spef",
    ],
    outs = [
        "gatelist_wc.txt",
    ],
    cmd = "wc -l $(locations :gatelist) $(locations :spef) > $@",
)

py_binary(
    name = "plot_clock_period_tool",
    srcs = [
        "plot_clock_period.py",
    ],
    main = "plot_clock_period.py",
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-pip//matplotlib",
        "@bazel-orfs-pip//pyyaml",
    ],
)

orfs_ppa(
    name = "plot",
    plot = ["lb_32x128_{}_cts".format(i + 1) for i in range(3)],
    title = "lb_32x128 variants",
)

[orfs_flow(
    name = "lb_32x128_{}".format(pdk),
    arguments = {
        "CORE_UTILIZATION": "5",
        "CORE_ASPECT_RATIO": "2",
    },
    pdk = "@docker_orfs//:" + pdk,
    sources = {
        "SDC_FILE": [":constraints-sram-sky130hd.sdc"],
    } | ({
        "FASTROUTE_TCL": [":fastroute.tcl"],
        "RULES_JSON": ["rules-base.json"],
    } if pdk == "sky130hd" else {}),
    tags = (["manual"] if pdk == "ihp-sg13g2" else []),
    top = "lb_32x128",
    verilog_files = LB_VERILOG_FILES,
) for pdk in [
    "sky130hd",
    "ihp-sg13g2",
]]

yosys(
    name = "alu",
    srcs = ["alu.v"],
    outs = ["alu.json"],
    arguments = [
        "-p",
        "read_verilog $(location alu.v); proc; write_json $(location alu.json)",
    ],
)

npm_link_all_packages(name = "node_modules")

js_binary(
    name = "netlistsvg",
    data = [
        "//:node_modules/netlistsvg",
        "//:node_modules/yargs",
    ],
    entry_point = "main.js",
    visibility = ["//visibility:public"],
)

netlistsvg(
    name = "alu_svg",
    src = "alu.json",
    out = "alu.svg",
)

# Demonstrate how to use this tool from a genrule
#
# https://docs.aspect.build/guides/rules_js_migration/#account-for-change-to-working-directory
genrule(
    name = "alu_svg_2",
    srcs = ["alu.json"],
    outs = ["alu2.svg"],
    cmd = """
BAZEL_BINDIR=$(BINDIR) $(location :netlistsvg) \
 ../../../$(location alu.json) \
 -o ../../../$(location alu2.svg)
""",
    tools = [":netlistsvg"],
)

# This should not be built with bazel build ..., as it fails
orfs_run(
    name = "cell_count_manual",
    src = ":lb_32x128_floorplan",
    outs = [
        "no-such-file-test.txt",
    ],
    extra_args = "> $WORK_HOME/test.txt",
    script = ":cell_count.tcl",
    tags = ["manual"],
)

# From any project using bazel-orfs run `bazelisk run @bazel-orfs//:bump`
# to upgrade ORFS and bazel-orfs.
sh_binary(
    name = "bump",
    srcs = ["bump.sh"],
    visibility = ["//visibility:public"],
)

# Not in use in CI
#
# pin_data(
#     name = "pin",
#     srcs = [
#         ":alu",
#     ],
#     artifacts_lock = "artifacts_lock.txt",
#     bucket = "some-google-bucket",
# )

# filegroup(
#     name = "foo",
#     srcs = [
#         "@pinned//alu",
#     ],
#     tags = ["manual"],
# )

# This library lists all the scala files we will be editing in vscode via bloop
chisel_library(
    name = "blooplib",
    srcs = [
        "//toolchains/scala:chiselfiles",
    ],
    deps = [
        "@maven//:org_scalatest_scalatest_2_13",
    ],
)

# Set up bloop
scala_bloop(
    name = "bloop",
    src = "blooplib",
)
