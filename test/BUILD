load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("@rules_python//python:defs.bzl", "py_binary", "py_test")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//:openroad.bzl", "get_stage_args", "orfs_floorplan", "orfs_flow", "orfs_gds", "orfs_macro", "orfs_run", "orfs_synth")
load("//:orfs_genrule.bzl", "orfs_genrule")
load("//:ppa.bzl", "orfs_ppa")
load("//:sweep.bzl", "orfs_sweep")

exports_files(
    glob([
        "**/*.sv",
        "**/*.sdc",
    ]),
    visibility = ["//:__subpackages__"],
)

filegroup(
    name = "io-sram",
    srcs = [
        ":io-sram.tcl",
    ],
    data = [
        ":util.tcl",
    ],
    visibility = ["//:__subpackages__"],
)

filegroup(
    name = "io",
    srcs = [
        ":io.tcl",
    ],
    data = [
        ":util.tcl",
    ],
    visibility = ["//:__subpackages__"],
)

filegroup(
    name = "constraints-sram",
    srcs = [
        ":constraints-sram.sdc",
    ],
    data = [
        ":util.tcl",
    ],
    visibility = ["//:__subpackages__"],
)

# Settings to speed up CI builds by disabling expensive operations that are
# only needed for timing closure and manufacturing sign-off.
#
# Setting                    Stage      What it disables
# -------                    -----      ----------------
# GPL_TIMING_DRIVEN=0        place      Timing-driven global placement. Skips timing path
#                                        analysis during placement iterations and buffer
#                                        removal (remove_buffers). (global_place.tcl)
# GPL_ROUTABILITY_DRIVEN=0   place      Routability-driven global placement. Skips routing
#                                        congestion estimation during placement. (global_place.tcl)
# SKIP_CTS_REPAIR_TIMING=1   cts        CTS timing repair. Skips repair_timing_helper after
#                                        clock tree synthesis — buffer insertion, gate sizing,
#                                        VT swapping. Can reduce CTS from hours to minutes
#                                        on large designs. (cts.tcl)
# SKIP_INCREMENTAL_REPAIR=1  grt        Incremental repair during global routing. Skips two
#                                        rounds of repair_design + repair_timing with
#                                        incremental re-routing between them. (global_route.tcl)
# REMOVE_ABC_BUFFERS=1       floorplan  Removes synthesis buffers instead of running
#                                        repair_timing_helper in floorplan. The alternative
#                                        (=0) runs hours of gate sizing/VT swapping.
#                                        (floorplan.tcl)
# SKIP_REPORT_METRICS=1      all        Metrics reporting. Skips report_checks, report_wns,
#                                        report_tns, report_power, report_clock_skew at every
#                                        stage. Saves minutes per stage. (report_metrics.tcl)
# FILL_CELLS=""               route      Fill cell insertion. Skips filler_placement for
#                                        manufacturing density requirements. (fillcell.tcl)
# TAPCELL_TCL=""              floorplan  Custom tap/endcap cell placement. Falls back to
#                                        simple cut_rows. (tapcell.tcl)
# PWR_NETS_VOLTAGES=""        final      IR drop analysis for power nets. Skips
#                                        analyze_power_grid. (final_report.tcl)
# GND_NETS_VOLTAGES=""        final      IR drop analysis for ground nets. Skips
#                                        analyze_power_grid. (final_report.tcl)
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

SRAM_ARGUMENTS = FAST_SETTINGS | {
    "IO_CONSTRAINTS": "$(location :io-sram)",
    "PLACE_DENSITY": "0.42",
    "PLACE_PINS_ARGS": "-min_distance 2 -min_distance_in_tracks",
    "SDC_FILE": "$(location :constraints-sram)",
}

BLOCK_FLOORPLAN = {
    "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    # repair_timing runs for hours in floorplan
    "REMOVE_ABC_BUFFERS": "1",
}

orfs_flow(
    name = "tag_array_64x184",
    abstract_stage = "cts",
    arguments = SRAM_ARGUMENTS | BLOCK_FLOORPLAN | {
        "CORE_ASPECT_RATIO": "10",
        "CORE_UTILIZATION": "20",
        "SKIP_REPORT_METRICS": "1",
    },
    # CI regression test for stage_arguments override of automatic stage assignment
    stage_arguments = {
        "floorplan": {
            "SKIP_REPORT_METRICS": "1",
        },
    },
    # FIXME reenable after https://github.com/The-OpenROAD-Project/OpenROAD/issues/7745 is fixed
    # mock_area = 0.8,
    stage_sources = {
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    substeps = False,
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = ["//:__subpackages__"],
)

LB_ARGS = SRAM_ARGUMENTS | {
    "CORE_ASPECT_RATIO": "2",
    "CORE_UTILIZATION": "30",
    "PLACE_DENSITY": "0.20",
    "PLACE_PINS_ARGS": "-min_distance 1 -min_distance_in_tracks",
}

LB_STAGE_SOURCES = {
    "floorplan": [":io-sram"],
    "place": [":io-sram"],
    "synth": [":constraints-sram"],
}

LB_VERILOG_FILES = ["mock/lb_32x128.sv"]

# Test a full abstract, all stages, so leave abstract_stage unset to default value(final)
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS | {
        "CORE_ASPECT_RATIO": "0.5",
        "CORE_UTILIZATION": "20",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    },
    mock_area = 0.7,
    stage_sources = LB_STAGE_SOURCES,
    substeps = False,
    verilog_files = LB_VERILOG_FILES,
    visibility = ["//optuna:__pkg__"],
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
    arguments = SRAM_ARGUMENTS | {
        "CORE_AREA": "2 2 23 23",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 25 25",
        "GDS_ALLOW_EMPTY": "lb_32x128",
        "GND_NETS_VOLTAGES": "",
        "MACRO_PLACE_HALO": "5 5",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "PLACE_DENSITY": "0.30",

        # Skip power checks to silence error and speed up build
        "PWR_NETS_VOLTAGES": "",
    },
    macros = ["lb_32x128_generate_abstract"],
    stage_sources = LB_STAGE_SOURCES,
    substeps = False,
    verilog_files = ["rtl/lb_32x128_top.v"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "place",
    arguments = LB_ARGS | {
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    },
    stage_sources = LB_STAGE_SOURCES,
    substeps = False,
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

orfs_sweep(
    name = "L1MetadataArray",
    abstract_stage = "cts",
    arguments = FAST_SETTINGS |
                {
                    "CORE_AREA": "2 2 18 68",
                    "CORE_MARGIN": "2",
                    "DIE_AREA": "0 0 20 70",
                    "GDS_ALLOW_EMPTY": "tag_array_64x184",
                    "MACRO_PLACE_HALO": "2 2",
                    "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
                    "PLACE_DENSITY": "0.30",
                    "SYNTH_HIERARCHICAL": "1",
                },
    sweep = {
        "1": {
            "macros": ["amalgam"],
            "sources": {
                "SDC_FILE": [":constraints-top.sdc"],
            },
        },
        "base": {
            "macros": ["tag_array_64x184_generate_abstract"],
            "sources": {
                "SDC_FILE": [":constraints-top.sdc"],
            },
        },
    },
    verilog_files = ["rtl/L1MetadataArray.sv"],
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
        "SDC_FILE": "$(location :constraints-combinational.sdc)",
        # Test locally, modify this, no re-synthesis should take place
        "PLACE_DENSITY": "0.53",
    },
    data = [":constraints-combinational.sdc"],
    module_top = "Mul",
    verilog_files = ["rtl/Mul.sv"],
)

filegroup(
    name = "Mul_synth_verilog",
    srcs = [
        "Mul_synth",
    ],
    output_group = "1_synth.v",
)

# Need full flow to test final gatelist extraction
orfs_flow(
    name = "regfile_128x65",
    arguments = SRAM_ARGUMENTS | BLOCK_FLOORPLAN | {
        "CORE_AREA": "2 2 23 23",
        "DIE_AREA": "0 0 25 25",
        "IO_CONSTRAINTS": "$(location :io-sram)",
        "PLACE_DENSITY": "0.30",
    },
    stage_sources = {
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    substeps = False,
    verilog_files = [
        "rtl/regfile_128x65.sv",
    ],
)

# buildifier: disable=duplicated-name
orfs_sweep(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    stage = "cts",
    stage_sources = {
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
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
    verilog_files = ["mock/lb_32x128.sv"],
)

filegroup(
    name = "gatelist",
    srcs = [
        "regfile_128x65_final",
    ],
    output_group = "6_final.v",
)

filegroup(
    name = "spef",
    srcs = [
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

# Same as gatelist_wc but using orfs_genrule to keep srcs in exec config.
# Native genrule forces srcs into target config, causing ORFS outputs to
# be rebuilt in a second configuration.
orfs_genrule(
    name = "gatelist_wc_orfs_genrule",
    srcs = [
        ":gatelist",
        ":spef",
    ],
    outs = [
        "gatelist_wc_orfs_genrule.txt",
    ],
    cmd = "wc -l $(locations :gatelist) $(locations :spef) > $@",
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

orfs_ppa(
    name = "plot",
    plot = ["lb_32x128_{}_cts".format(i + 1) for i in range(3)],
    title = "lb_32x128 variants",
)

orfs_gds(
    name = "lb_32x128_sky130hd_gds",
    src = "//test/smoketest:lb_32x128_sky130hd_final",
    klayout = "@mock-klayout//src/bin:klayout",
    variant = "base",
)

orfs_macro(
    name = "lb_32x128_sky130hd_macro",
    gds = ":lb_32x128_sky130hd_gds",
    lef = "//test/smoketest:lb_32x128_sky130hd_generate_abstract",
    lib = "//test/smoketest:lb_32x128_sky130hd_generate_abstract",
    module_top = "lb_32x128",
)

sh_test(
    name = "lb_32x128_sky130hd_macro_test",
    srcs = ["macro_test.sh"],
    args = [
        "$(locations :lb_32x128_sky130hd_macro)",
    ],
    data = [":lb_32x128_sky130hd_macro"],
)

# Test the openroad override mechanism using mock-openroad (fast in CI).
# Also tests the last_stage option to stop after floorplan without abstract.
# Test the openroad override mechanism using mock-openroad (fast in CI).
# Also tests the last_stage option to stop after floorplan without abstract.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    openroad = "@mock-openroad//src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock_openroad",
    verilog_files = LB_VERILOG_FILES,
)

# Manual target for testing the source-built OpenROAD GUI locally.
# Run: bazelisk run //test:lb_32x128_openroad_gui_synth
# This builds OpenROAD from source with GUI and opens the synthesis
# results in the OpenROAD GUI. Use after `bazelisk run //:bump` to
# verify the latest OpenROAD works with the flow.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    openroad = "@openroad//:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    stage_sources = LB_STAGE_SOURCES,
    tags = ["manual"],
    variant = "openroad_gui",
    verilog_files = LB_VERILOG_FILES,
)

# Test squashed flow through cts: all stages after synth run as a single
# Bazel action. substeps=False disables substep target generation.
# Shares mock_openroad synth to avoid conflicting action with other flows.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    openroad = "@mock-openroad//src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    squash = True,
    stage_sources = LB_STAGE_SOURCES,
    variant = "squashed",
    verilog_files = LB_VERILOG_FILES,
)

# Test squashed flow through final: exercises grt, route, and final stages
# in squashed mode, with substep targets enabled.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "final",
    openroad = "@mock-openroad//src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    squash = True,
    stage_sources = LB_STAGE_SOURCES,
    substeps = True,
    variant = "squashed_final",
    verilog_files = LB_VERILOG_FILES,
)

sh_test(
    name = "lb_32x128_squashed_final_test",
    srcs = ["squashed_test.sh"],
    data = [":lb_32x128_squashed_final_final"],
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

py_binary(
    name = "plot_repair",
    srcs = ["plot-retiming.py"],
    main = "plot-retiming.py",
    visibility = ["//visibility:public"],
    deps = ["@bazel-orfs-features-pip//matplotlib"],
)

# --- Mock unit tests ---

py_test(
    name = "mock_openroad_test",
    srcs = [
        "mock_helpers.py",
        "mock_openroad_test.py",
    ],
    data = ["@mock-openroad//src/bin:openroad.py"],
    imports = ["."],
)

py_test(
    name = "mock_klayout_test",
    srcs = [
        "mock_helpers.py",
        "mock_klayout_test.py",
    ],
    data = ["@mock-klayout//src/bin:klayout.py"],
    imports = ["."],
)

# --- Mock-openroad build tests: fast validation of .bzl rule logic ---

build_test(
    name = "mock_openroad_floorplan_build_test",
    targets = [":lb_32x128_mock_openroad_floorplan"],
)

build_test(
    name = "mock_openroad_squashed_cts_build_test",
    targets = [":lb_32x128_squashed_cts"],
)

# Mock hierarchical flow: tests macros attribute with mock-openroad.
# lb_32x128_mock_openroad generates abstract (submacro), then
# lb_32x128_mock_hierarchy uses it as a macro (parent with macro).
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS | BLOCK_FLOORPLAN,
    openroad = "@mock-openroad//src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock_abstract",
    verilog_files = LB_VERILOG_FILES,
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128_top",
    abstract_stage = "place",
    arguments = SRAM_ARGUMENTS | {
        "CORE_AREA": "2 2 23 23",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 25 25",
        "GDS_ALLOW_EMPTY": "lb_32x128",
        "MACRO_PLACE_HALO": "5 5",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "PLACE_DENSITY": "0.30",
        "PWR_NETS_VOLTAGES": "",
    },
    macros = ["lb_32x128_mock_abstract_generate_abstract"],
    openroad = "@mock-openroad//src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_top_synth"},
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock_hierarchy",
    verilog_files = ["rtl/lb_32x128_top.v"],
)

build_test(
    name = "mock_hierarchy_build_test",
    targets = [":lb_32x128_top_mock_hierarchy_generate_abstract"],
)

# Mock sweep test: tests orfs_sweep with macros + openroad override.
# Uses mock-openroad for all stages. The sweep's "base" variant uses
# lb_32x128_mock_abstract as a macro (hierarchical design).
orfs_sweep(
    name = "mock_sweep_lb",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    openroad = "@mock-openroad//src/bin:openroad",
    stage_sources = LB_STAGE_SOURCES,
    sweep = {
        "mock": {
            "macros": ["lb_32x128_mock_abstract_generate_abstract"],
            "previous_stage": {"floorplan": "lb_32x128_synth"},
            "sources": {
                "SDC_FILE": [":constraints-sram"],
            },
        },
    },
    verilog_files = ["rtl/L1MetadataArray.sv"],
)

build_test(
    name = "mock_sweep_build_test",
    targets = [":mock_sweep_lb_mock_generate_abstract"],
)
# Pruning is validated implicitly: if orfs_sweep's previous_stage pruning
# is broken, the lb_32x128 sweep targets would fail at analysis time
# (duplicate actions or missing deps). No explicit query tests needed.
