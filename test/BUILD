load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("@rules_python//python:defs.bzl", "py_test")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//:openroad.bzl", "get_stage_args", "orfs_floorplan", "orfs_flow", "orfs_gds", "orfs_macro", "orfs_run", "orfs_synth")
load("//:orfs_genrule.bzl", "orfs_genrule")
load("//:sweep.bzl", "orfs_sweep")
load(":deps_output_group_rule.bzl", "deps_output_group_test", "output_group_test")

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
    "GLOBAL_PLACEMENT_ARGS": "-overflow 0.2",
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
    "PLACE_DENSITY": "0.65",
    "PLACE_PINS_ARGS": "-min_distance 2 -min_distance_in_tracks",
    "SDC_FILE": "$(location :constraints-sram)",
}

BLOCK_FLOORPLAN = {
    "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    # repair_timing runs for hours in floorplan
    "REMOVE_ABC_BUFFERS": "1",
}

TAG_ARRAY_ARGUMENTS = SRAM_ARGUMENTS | BLOCK_FLOORPLAN | {
    "CORE_AREA": "1.026 1.080 5.184 42.930",
    "DIE_AREA": "0 0 6.198 43.980",
    "SKIP_REPORT_METRICS": "1",
}

orfs_sweep(
    name = "tag_array_64x184",
    abstract_stage = "cts",
    arguments = TAG_ARRAY_ARGUMENTS,
    # Pin placement variant: runs floorplan without pinned IO for regeneration.
    other_variants = {
        "pin_placement": {
            "last_stage": "floorplan",
            "previous_stage": {"floorplan": "tag_array_64x184_synth"},
            "stage_sources": {
                "floorplan": [":io-sram"],
            },
            "tags": ["manual"],
        },
    },
    stage_sources = {
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    sweep = {
        "base": {
            "arguments": {
                "IO_CONSTRAINTS": "$(location :tag_array_64x184_io-placement.tcl)",
            },
            # CI regression test for stage_arguments override of automatic stage assignment
            "stage_arguments": {
                "floorplan": {
                    "SKIP_REPORT_METRICS": "1",
                },
            },
            "stage_sources": {
                "floorplan": [":tag_array_64x184_io-placement.tcl"],
            },
        },
    },
    verilog_files = ["//another:tag_array_64x184.sv"],
    visibility = ["//:__subpackages__"],
)

orfs_run(
    name = "tag_array_64x184_write_pin_placement",
    src = ":tag_array_64x184_pin_placement_floorplan",
    outs = [
        "tag_array_64x184_io-placement.tcl",
    ],
    arguments = {
        "OUTPUT": "tag_array_64x184_io-placement.tcl",
    },
    script = ":write_pin_placement.tcl",
    tags = ["manual"],
)

sh_binary(
    name = "pin_tag_array_64x184",
    srcs = ["pin_placement.sh"],
    args = [
        "$(rootpath :tag_array_64x184_write_pin_placement)",
        "test/tag_array_64x184_io-placement.tcl",
    ],
    data = [":tag_array_64x184_write_pin_placement"],
    tags = ["manual"],
)

LB_ARGS = SRAM_ARGUMENTS | {
    "CORE_ASPECT_RATIO": "2",
    "CORE_UTILIZATION": "40",
    "PLACE_DENSITY": "0.65",
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
        "CORE_AREA": "1.026 1.080 6.372 3.510",
        "CORE_ASPECT_RATIO": "",
        "CORE_UTILIZATION": "",
        "DIE_AREA": "0 0 7.400 4.700",
        "IO_CONSTRAINTS": "$(location :lb_32x128_io-placement.tcl)",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    },
    mock_area = 0.7,
    stage_sources = {
        "floorplan": [":lb_32x128_io-placement.tcl"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    verilog_files = LB_VERILOG_FILES,
    visibility = [],
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
        "IO_CONSTRAINTS": "$(location :lb_32x128_top_io-placement.tcl)",
        "MACRO_PLACE_HALO": "5 5",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "PLACE_DENSITY": "0.65",

        # Skip power checks to silence error and speed up build
        "PWR_NETS_VOLTAGES": "",
    },
    macros = ["lb_32x128_generate_abstract"],
    stage_sources = {
        "floorplan": [":lb_32x128_top_io-placement.tcl"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    verilog_files = ["rtl/lb_32x128_top.v"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128_top",
    arguments = SRAM_ARGUMENTS | {
        "CORE_AREA": "2 2 23 23",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 25 25",
        "MACRO_PLACE_HALO": "5 5",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "PLACE_DENSITY": "0.65",
    },
    last_stage = "floorplan",
    macros = ["lb_32x128_generate_abstract"],
    previous_stage = {"floorplan": ":lb_32x128_top_synth"},
    stage_sources = LB_STAGE_SOURCES,
    tags = ["manual"],
    variant = "pin_placement",
    verilog_files = ["rtl/lb_32x128_top.v"],
)

orfs_run(
    name = "lb_32x128_top_write_pin_placement",
    src = ":lb_32x128_top_pin_placement_floorplan",
    outs = [
        "lb_32x128_top_io-placement.tcl",
    ],
    arguments = {
        "OUTPUT": "lb_32x128_top_io-placement.tcl",
    },
    script = ":write_pin_placement.tcl",
    tags = ["manual"],
)

sh_binary(
    name = "pin_lb_32x128_top",
    srcs = ["pin_placement.sh"],
    args = [
        "$(rootpath :lb_32x128_top_write_pin_placement)",
        "test/lb_32x128_top_io-placement.tcl",
    ],
    data = [":lb_32x128_top_write_pin_placement"],
    tags = ["manual"],
)

# Test variant naming: reuses base floorplan, runs place + cts + abstract.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    stage_sources = LB_STAGE_SOURCES,
    variant = "test",
    verilog_files = LB_VERILOG_FILES,
)

# Pin placement generation: shares synth, runs own floorplan without pinned IO.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    stage_sources = LB_STAGE_SOURCES,
    tags = ["manual"],
    variant = "pin_placement",
    verilog_files = LB_VERILOG_FILES,
)

orfs_run(
    name = "lb_32x128_write_pin_placement",
    src = ":lb_32x128_pin_placement_floorplan",
    outs = [
        "lb_32x128_io-placement.tcl",
    ],
    arguments = {
        "OUTPUT": "lb_32x128_io-placement.tcl",
    },
    script = ":write_pin_placement.tcl",
    tags = ["manual"],
)

sh_binary(
    name = "pin_lb_32x128",
    srcs = ["pin_placement.sh"],
    args = [
        "$(rootpath :lb_32x128_write_pin_placement)",
        "test/lb_32x128_io-placement.tcl",
    ],
    data = [":lb_32x128_write_pin_placement"],
    tags = ["manual"],
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

L1_ARGUMENTS = FAST_SETTINGS | {
    "CORE_AREA": "2 2 18 68",
    "CORE_MARGIN": "2",
    "DIE_AREA": "0 0 20 70",
    "GDS_ALLOW_EMPTY": "tag_array_64x184",
    "MACRO_PLACE_HALO": "2 2",
    "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
    "PLACE_DENSITY": "0.65",
    "SYNTH_HIERARCHICAL": "1",
}

orfs_sweep(
    name = "L1MetadataArray",
    abstract_stage = "cts",
    arguments = L1_ARGUMENTS,
    other_variants = {
        "pin_placement": {
            "last_stage": "floorplan",
            "macros": ["tag_array_64x184_generate_abstract"],
            "previous_stage": {"floorplan": "L1MetadataArray_synth"},
            "sources": {
                "SDC_FILE": [":constraints-top.sdc"],
            },
            "tags": ["manual"],
        },
    },
    sweep = {
        "1": {
            "arguments": {
                "IO_CONSTRAINTS": "$(location :L1MetadataArray_io-placement.tcl)",
            },
            "macros": ["amalgam"],
            "sources": {
                "SDC_FILE": [":constraints-top.sdc"],
            },
            "stage_sources": {
                "floorplan": [":L1MetadataArray_io-placement.tcl"],
            },
        },
        "base": {
            "arguments": {
                "IO_CONSTRAINTS": "$(location :L1MetadataArray_io-placement.tcl)",
            },
            "macros": ["tag_array_64x184_generate_abstract"],
            "sources": {
                "SDC_FILE": [":constraints-top.sdc"],
            },
            "stage_sources": {
                "floorplan": [":L1MetadataArray_io-placement.tcl"],
            },
        },
    },
    verilog_files = ["rtl/L1MetadataArray.sv"],
)

orfs_run(
    name = "L1MetadataArray_write_pin_placement",
    src = ":L1MetadataArray_pin_placement_floorplan",
    outs = [
        "L1MetadataArray_io-placement.tcl",
    ],
    arguments = {
        "OUTPUT": "L1MetadataArray_io-placement.tcl",
    },
    script = ":write_pin_placement.tcl",
    tags = ["manual"],
)

sh_binary(
    name = "pin_L1MetadataArray",
    srcs = ["pin_placement.sh"],
    args = [
        "$(rootpath :L1MetadataArray_write_pin_placement)",
        "test/L1MetadataArray_io-placement.tcl",
    ],
    data = [":L1MetadataArray_write_pin_placement"],
    tags = ["manual"],
)

orfs_run(
    name = "check_mock_area",
    src = ":L1MetadataArray_floorplan",
    outs = [
        "area_ok.txt",
    ],
    script = ":check_mock_area.tcl",
    tags = ["manual"],
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

# Test SYNTH_KEPT_MODULES: skip keep-hierarchy discovery, go straight to
# parallel partition synthesis with a pre-specified module list.
orfs_synth(
    name = "kept_modules_synth",
    arguments = {
        "SDC_FILE": "$(location :constraints-top.sdc)",
        "SYNTH_KEPT_MODULES": "adder counter",
    },
    data = [":constraints-top.sdc"],
    module_top = "kept_modules_top",
    verilog_files = ["rtl/kept_modules_top.v"],
)

build_test(
    name = "kept_modules_synth_test",
    targets = [":kept_modules_synth"],
)

REGFILE_ARGUMENTS = SRAM_ARGUMENTS | BLOCK_FLOORPLAN | {
    "CORE_AREA": "1.026 1.080 4.914 4.860",
    "DIE_AREA": "0 0 5.940 5.940",
    "PLACE_DENSITY": "0.65",
}

# Need full flow to test final gatelist extraction.
# Tagged manual — needs real OpenROAD for valid metrics.
orfs_sweep(
    name = "regfile_128x65",
    arguments = REGFILE_ARGUMENTS,
    other_variants = {
        "pin_placement": {
            "last_stage": "floorplan",
            "previous_stage": {"floorplan": "regfile_128x65_synth"},
            "stage_sources": {
                "floorplan": [":io-sram"],
            },
            "tags": ["manual"],
        },
    },
    stage_sources = {
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    sweep = {
        "base": {
            "arguments": {
                "IO_CONSTRAINTS": "$(location :regfile_128x65_io-placement.tcl)",
            },
            "stage_sources": {
                "floorplan": [":regfile_128x65_io-placement.tcl"],
            },
        },
    },
    tags = ["manual"],
    verilog_files = [
        "rtl/regfile_128x65.sv",
    ],
)

orfs_run(
    name = "regfile_128x65_write_pin_placement",
    src = ":regfile_128x65_pin_placement_floorplan",
    outs = [
        "regfile_128x65_io-placement.tcl",
    ],
    arguments = {
        "OUTPUT": "regfile_128x65_io-placement.tcl",
    },
    script = ":write_pin_placement.tcl",
    tags = ["manual"],
)

sh_binary(
    name = "pin_regfile_128x65",
    srcs = ["pin_placement.sh"],
    args = [
        "$(rootpath :regfile_128x65_write_pin_placement)",
        "test/regfile_128x65_io-placement.tcl",
    ],
    data = [":regfile_128x65_write_pin_placement"],
    tags = ["manual"],
)

# buildifier: disable=duplicated-name
orfs_sweep(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    other_variants = {
        "sweep_pin_placement": {
            "last_stage": "floorplan",
            "previous_stage": {"floorplan": "lb_32x128_synth"},
            "tags": ["manual"],
        },
    },
    stage = "cts",
    stage_sources = {
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    sweep = {
        "1": {
            "arguments": {
                "CORE_AREA": "1.026 1.080 3.672 6.210",
                "CORE_ASPECT_RATIO": "",
                "CORE_UTILIZATION": "",
                "DIE_AREA": "0 0 4.700 7.400",
                "IO_CONSTRAINTS": "$(location :lb_32x128_sweep_io-placement.tcl)",
                "PLACE_DENSITY": "0.65",
            },
            "previous_stage": {"floorplan": "lb_32x128_synth"},
            "stage_sources": {
                "floorplan": [":lb_32x128_sweep_io-placement.tcl"],
            },
        },
        "2": {
            "arguments": {
                "PLACE_DENSITY": "0.66",
            },
            "previous_stage": {"place": "lb_32x128_floorplan"},
        },
        "3": {
            "arguments": {
                "PLACE_DENSITY": "0.67",
            },
            "previous_stage": {"cts": "lb_32x128_place"},
        },
    },
    verilog_files = ["mock/lb_32x128.sv"],
)

orfs_run(
    name = "lb_32x128_sweep_write_pin_placement",
    src = ":lb_32x128_sweep_pin_placement_floorplan",
    outs = [
        "lb_32x128_sweep_io-placement.tcl",
    ],
    arguments = {
        "OUTPUT": "lb_32x128_sweep_io-placement.tcl",
    },
    script = ":write_pin_placement.tcl",
    tags = ["manual"],
)

sh_binary(
    name = "pin_lb_32x128_sweep",
    srcs = ["pin_placement.sh"],
    args = [
        "$(rootpath :lb_32x128_sweep_write_pin_placement)",
        "test/lb_32x128_sweep_io-placement.tcl",
    ],
    data = [":lb_32x128_sweep_write_pin_placement"],
    tags = ["manual"],
)

filegroup(
    name = "gatelist",
    srcs = [
        "regfile_128x65_final",
    ],
    output_group = "6_final.v",
    tags = ["manual"],
)

filegroup(
    name = "spef",
    srcs = [
        "regfile_128x65_final",
    ],
    output_group = "6_final.spef",
    tags = ["manual"],
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
    tags = ["manual"],
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
    tags = ["manual"],
)

# Exercise real OpenSTA from the OpenROAD source build.
# Requires: bazel_dep(name = "openroad") + git_override in MODULE.bazel.
orfs_run(
    name = "sta",
    src = ":lb_32x128_floorplan",
    outs = [
        "units.txt",
    ],
    arguments = {
        "OUTPUT": "$(location units.txt)",
    },
    openroad = "@openroad//src/sta:opensta",
    script = ":units.tcl",
    tags = ["manual"],
)

build_test(
    name = "sta_test",
    tags = ["manual"],
    targets = [":sta"],
)

orfs_gds(
    name = "lb_32x128_sky130hd_gds",
    src = "//test/smoketest:lb_32x128_sky130hd_final",
    klayout = "@mock-klayout//src/bin:klayout",
    tags = ["manual"],
    variant = "base",
)

orfs_macro(
    name = "lb_32x128_sky130hd_macro",
    gds = ":lb_32x128_sky130hd_gds",
    lef = "//test/smoketest:lb_32x128_sky130hd_generate_abstract",
    lib = "//test/smoketest:lb_32x128_sky130hd_generate_abstract",
    module_top = "lb_32x128",
    tags = ["manual"],
)

sh_test(
    name = "lb_32x128_sky130hd_macro_test",
    srcs = ["macro_test.sh"],
    args = [
        "$(locations :lb_32x128_sky130hd_macro)",
    ],
    data = [":lb_32x128_sky130hd_macro"],
    tags = ["manual"],
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
    openroad = "//mock/openroad/src/bin:openroad",
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
# Bazel action. Shares mock_openroad synth to avoid conflicting action.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    squash = True,
    stage_sources = LB_STAGE_SOURCES,
    variant = "squashed",
    verilog_files = LB_VERILOG_FILES,
)

# Test squashed flow through final: exercises grt, route, and final stages
# in squashed mode.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "final",
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    squash = True,
    stage_sources = LB_STAGE_SOURCES,
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

# --- Mock unit tests ---

py_test(
    name = "mock_openroad_test",
    srcs = [
        "mock_helpers.py",
        "mock_openroad_test.py",
    ],
    data = [
        "//mock/openroad/src/bin:openroad.py",
        "//mock/openroad/src/bin:openroad_commands.py",
        "//mock/openroad/src/bin:tcl_interpreter.py",
    ],
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

py_test(
    name = "openroad_commands_test",
    srcs = [
        "//mock/openroad/src/bin:openroad_commands.py",
        "//mock/openroad/src/bin:openroad_commands_test.py",
        "//mock/openroad/src/bin:tcl_interpreter.py",
    ],
    imports = ["."],
    deps = ["@bazel-orfs-pip//pytest"],
)

py_test(
    name = "tcl_interpreter_test",
    srcs = [
        "//mock/openroad/src/bin:tcl_interpreter.py",
        "//mock/openroad/src/bin:tcl_interpreter_test.py",
    ],
    imports = ["."],
    deps = ["@bazel-orfs-pip//pytest"],
)

py_test(
    name = "yosys_commands_test",
    srcs = ["yosys_commands_test_wrapper.py"],
    data = [
        "//mock/openroad/src/bin:tcl_interpreter.py",
        "//mock/yosys/src/bin:yosys_commands.py",
        "//mock/yosys/src/bin:yosys_commands_test.py",
    ],
    main = "yosys_commands_test_wrapper.py",
    deps = ["@bazel-orfs-pip//pytest"],
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
    openroad = "//mock/openroad/src/bin:openroad",
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
        "PLACE_DENSITY": "0.65",
        "PWR_NETS_VOLTAGES": "",
    },
    macros = ["lb_32x128_mock_abstract_generate_abstract"],
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_top_synth"},
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock_hierarchy",
    verilog_files = ["rtl/lb_32x128_top.v"],
)

build_test(
    name = "mock_hierarchy_build_test",
    targets = [":lb_32x128_top_mock_hierarchy_generate_abstract"],
)

# Test that ADDITIONAL_LEFS from sources (config.mk) and deps (macros)
# are merged, not overridden. Without merge_arguments(), the dep LEF
# would silently replace the source LEF.
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
        "PLACE_DENSITY": "0.65",
        "PWR_NETS_VOLTAGES": "",
    },
    macros = ["lb_32x128_mock_abstract_generate_abstract"],
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_top_synth"},
    sources = {
        "ADDITIONAL_LEFS": [":dummy_extra.lef"],
    },
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock_hierarchy_merge",
    verilog_files = ["rtl/lb_32x128_top.v"],
)

build_test(
    name = "mock_hierarchy_merge_build_test",
    targets = [":lb_32x128_top_mock_hierarchy_merge_generate_abstract"],
)

# Mock sweep test: tests orfs_sweep with macros + openroad override.
# Uses mock-openroad for all stages. The sweep's "base" variant uses
# lb_32x128_mock_abstract as a macro (hierarchical design).
orfs_sweep(
    name = "mock_sweep_lb",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    openroad = "//mock/openroad/src/bin:openroad",
    stage_sources = LB_STAGE_SOURCES,
    sweep = {
        "sweep": {
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
    targets = [":mock_sweep_lb_sweep_generate_abstract"],
)
# Pruning is validated implicitly: if orfs_sweep's previous_stage pruning
# is broken, the lb_32x128 sweep targets would fail at analysis time
# (duplicate actions or missing deps). No explicit query tests needed.

# --- Lint flow tests: verify that heavy dependencies are excluded ---

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    lint = True,
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    stage_sources = LB_STAGE_SOURCES,
    variant = "lite",
    verilog_files = LB_VERILOG_FILES,
)

build_test(
    name = "lint_build_test",
    targets = [":lb_32x128_lite_floorplan"],
)

sh_test(
    name = "lint_no_heavy_deps_test",
    srcs = ["lint_test.sh"],
    data = [":lb_32x128_lite_floorplan"],
)

# --- User-facing binary tests: verify binaries work with mock environments ---

py_test(
    name = "fix_lint_test",
    srcs = ["fix_lint_test.py"],
    deps = ["//:fix_lint_lib"],
)

sh_test(
    name = "klayout_wrapper_test",
    srcs = ["tool_wrapper_test.sh"],
    args = [
        "$(rootpath //:klayout)",
        "klayout",
    ],
    data = ["//:klayout"],
)

sh_test(
    name = "openroad_wrapper_test",
    srcs = ["tool_wrapper_test.sh"],
    args = [
        "$(rootpath //:openroad)",
        "openroad",
    ],
    data = ["//:openroad"],
)

# --- Fully-mock flows for deps integration tests ---
# These use mock-yosys (synth) + mock-openroad (other stages) so the
# deps integration test script needs no real tool builds.

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    openroad = "//mock/openroad/src/bin:openroad",
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock",
    verilog_files = LB_VERILOG_FILES,
    yosys = "//mock/yosys/src/bin:yosys",
)

# Cross-package verilog (//another:) exercises external package handling.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "tag_array_64x184",
    arguments = TAG_ARRAY_ARGUMENTS,
    last_stage = "floorplan",
    openroad = "//mock/openroad/src/bin:openroad",
    stage_sources = {
        "floorplan": [":io-sram"],
        "place": [":io-sram"],
        "synth": [":constraints-sram"],
    },
    variant = "mock",
    verilog_files = ["//another:tag_array_64x184.sv"],
    yosys = "//mock/yosys/src/bin:yosys",
)

# Fully-mock abstract chain: reuses lb_32x128_mock_synth, adds
# mock-openroad floorplan through cts for abstract generation.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = LB_ARGS | BLOCK_FLOORPLAN,
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_mock_synth"},
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock_full_abstract",
    verilog_files = LB_VERILOG_FILES,
)

# Fully-mock hierarchical flow for deps integration tests.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128_top",
    arguments = SRAM_ARGUMENTS | {
        "CORE_AREA": "2 2 23 23",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 25 25",
        "GDS_ALLOW_EMPTY": "lb_32x128",
        "MACRO_PLACE_HALO": "5 5",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "PLACE_DENSITY": "0.65",
        "PWR_NETS_VOLTAGES": "",
    },
    last_stage = "floorplan",
    macros = ["lb_32x128_mock_full_abstract_generate_abstract"],
    openroad = "//mock/openroad/src/bin:openroad",
    stage_sources = LB_STAGE_SOURCES,
    variant = "mock_full_hierarchy",
    verilog_files = ["rtl/lb_32x128_top.v"],
    yosys = "//mock/yosys/src/bin:yosys",
)

# --- Deps deploy tests: verify end-to-end deploy workflow ---
# These replace deps_integration_test.sh with Bazel-native tests
# that receive pre-built tarballs — no nested bazelisk calls.

sh_test(
    name = "deps_deploy_synth_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_mock_synth_deps.tar.gz)",
        "dir_exists",
    ],
    data = [":lb_32x128_mock_synth_deps.tar.gz"],
)

sh_test(
    name = "deps_deploy_floorplan_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_mock_floorplan_deps.tar.gz)",
        "print_flow_home",
    ],
    data = [":lb_32x128_mock_floorplan_deps.tar.gz"],
)

sh_test(
    name = "deps_deploy_real_floorplan_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :tag_array_64x184_mock_floorplan_deps.tar.gz)",
        "print_flow_home",
    ],
    data = [":tag_array_64x184_mock_floorplan_deps.tar.gz"],
)

sh_test(
    name = "deps_deploy_hierarchy_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_top_mock_full_hierarchy_floorplan_deps.tar.gz)",
        "config_contains",
        "ADDITIONAL_LEFS",
    ],
    data = [":lb_32x128_top_mock_full_hierarchy_floorplan_deps.tar.gz"],
)

sh_test(
    name = "deps_deploy_make_passthrough_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :tag_array_64x184_mock_floorplan_deps.tar.gz)",
        "make_passthrough",
    ],
    data = [":tag_array_64x184_mock_floorplan_deps.tar.gz"],
)

sh_test(
    name = "deps_deploy_run_substep_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :tag_array_64x184_mock_floorplan_deps.tar.gz)",
        "run_substep",
    ],
    data = [":tag_array_64x184_mock_floorplan_deps.tar.gz"],
)

# --- Deps pkg_tar tests: verify on-demand deps deployment ---

# Test deps tarball on synth (yosys) stage
deps_output_group_test(
    name = "deps_output_group_synth_test",
    target = ":lb_32x128_synth_deps",
)

# Test deps tarball on floorplan (openroad) stage
deps_output_group_test(
    name = "deps_output_group_floorplan_test",
    target = ":lb_32x128_mock_openroad_floorplan_deps",
)

# Test deps tarball on squashed flow stage
deps_output_group_test(
    name = "deps_output_group_squashed_test",
    target = ":lb_32x128_squashed_final_final_deps",
)

# --- Substep output group tests: verify per-substep .odb caching ---

# Flow with substeps=True to test intermediate .odb capture
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    stage_sources = LB_STAGE_SOURCES,
    substeps = True,
    variant = "substeps",
    verilog_files = LB_VERILOG_FILES,
)

# First substep: verifies chain starts correctly
output_group_test(
    name = "substep_first_output_group_test",
    output_group = "substep_2_1_floorplan",
    target = ":lb_32x128_substeps_floorplan",
)

# Last substep: verifies no conflict with final 2_floorplan.odb result
output_group_test(
    name = "substep_last_output_group_test",
    output_group = "substep_2_4_floorplan_pdn",
    target = ":lb_32x128_substeps_floorplan",
)

# deps tarball still works alongside substeps=True
deps_output_group_test(
    name = "deps_output_group_substeps_test",
    target = ":lb_32x128_substeps_floorplan_deps",
)
