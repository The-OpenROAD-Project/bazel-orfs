load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_python//python:defs.bzl", "py_test")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//:openroad.bzl", "orfs_arguments", "orfs_floorplan", "orfs_flow", "orfs_gds", "orfs_macro", "orfs_place", "orfs_run", "orfs_run_executable", "orfs_synth", "orfs_test", "orfs_variables")
load("//:orfs_genrule.bzl", "orfs_genrule")
load("//:sweep.bzl", "orfs_sweep")
load(":deps_output_group_rule.bzl", "deps_output_group_test", "output_group_test")
load(":keep_modules_test.bzl", "keep_modules_test_suite")
load(":provider_test_rule.bzl", "lib_pre_layout_test")
load(":quick_pins_test_rule.bzl", "quick_pins_data_dep_test")
load(":sdc_clock_period_test.bzl", "runfiles_contents_test", "synth_action_inputs_test")
load(":source_input_propagation_test.bzl", "source_input_propagation_test")
load(":stages_filter_test.bzl", "stages_filter_test_suite")
load(":work_home_test.bzl", "work_home_test_suite")

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
    "PLACE_DENSITY": "0.65",
    "PLACE_PINS_ARGS": "-min_distance 2 -min_distance_in_tracks",
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
            "sources": {
                "IO_CONSTRAINTS": [":io-sram"],
            },
            "tags": ["manual"],
        },
    },
    sources = {
        "IO_CONSTRAINTS": [":io-sram"],
        "SDC_FILE": [":constraints-sram"],
    },
    sweep = {
        "base": {
            "sources": {
                "IO_CONSTRAINTS": [":tag_array_64x184_io-placement.tcl"],
            },
            # CI regression test for stage_arguments override of automatic stage assignment
            "stage_arguments": {
                "floorplan": {
                    "SKIP_REPORT_METRICS": "1",
                },
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

LB_SOURCES = {
    "IO_CONSTRAINTS": [":io-sram"],
    "SDC_FILE": [":constraints-sram"],
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
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
    },
    mock_area = 0.7,
    sources = {
        "IO_CONSTRAINTS": [":lb_32x128_io-placement.tcl"],
        "SDC_FILE": [":constraints-sram"],
    },
    verilog_files = LB_VERILOG_FILES,
    visibility = [],
)

# buildifier: disable=duplicated-name
# Standalone stage target sharing another flow's synth.  It hands the macro
# the same undifferentiated LB_ARGS/LB_SOURCES dicts an orfs_flow() gets and
# relies on it to keep only what floorplan owns — the filtering used to be
# spelled out here with a call-site get_stage_args(["floorplan"], ...) and a
# hand-picked LB_SOURCES["IO_CONSTRAINTS"].
orfs_floorplan(
    name = "lb_32x128_shared_synth_floorplan",
    src = ":lb_32x128_synth",
    arguments = LB_ARGS,
    sources = LB_SOURCES,
    variant = "blah",
)

# Standalone stage macros get the full orfs_flow treatment: undifferentiated
# arguments=/sources= dicts filtered down to the stage, extra_arguments keyed
# by stage the way orfs_flow takes it, and user_arguments/user_sources as the
# spell-check escape hatch.  Analysis alone is the assertion here:
#   * a stage-keyed extra_arguments dict reaching the rule unnarrowed would be
#     a dict where a label_list is expected;
#   * an unfiltered sources= would emit $(locations) for a label the stage
#     pruned from data, which is a location-expansion error; and
#   * post-#820 a stage the macro failed to declare is a hard fail() in
#     _make_impl rather than a silently empty allow-list.
orfs_place(
    name = "lb_32x128_standalone_place",
    src = ":lb_32x128_floorplan",
    arguments = LB_ARGS,
    extra_arguments = {"place": [":lb_32x128_auto_utilization"]},
    sources = LB_SOURCES,
    tags = ["manual"],
    user_arguments = {"USER_PROJECT_KNOB": "42"},
    variant = "standalone",
)

build_test(
    name = "lb_32x128_standalone_place_build_test",
    targets = [":lb_32x128_standalone_place"],
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
        "PLACE_DENSITY": "0.65",

        # Skip power checks to silence error and speed up build
        "PWR_NETS_VOLTAGES": "",
    },
    macros = ["lb_32x128_generate_abstract"],
    sources = {
        "IO_CONSTRAINTS": [":lb_32x128_top_io-placement.tcl"],
        "SDC_FILE": [":constraints-sram"],
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
    sources = LB_SOURCES,
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
    sources = LB_SOURCES,
    variant = "test",
    verilog_files = LB_VERILOG_FILES,
)

# Exercises user_arguments: project-specific env vars that intentionally
# bypass the variables.yaml spell-check.  Loading this target proves the
# feature works; `bazelisk test //...` picks it up via build_test below.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    sources = LB_SOURCES,
    user_arguments = {
        "ARRAY_COLS": "4",
        "USER_PROJECT_KNOB": "42",
    },
    variant = "user_args",
    verilog_files = LB_VERILOG_FILES,
)

build_test(
    name = "lb_32x128_user_args_build_test",
    targets = [":lb_32x128_user_args_floorplan"],
)

# Pin placement generation: shares synth, runs own floorplan without pinned IO.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "floorplan",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    sources = LB_SOURCES,
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

# Auto-utilization: computes CORE_UTILIZATION and PLACE_DENSITY from synthesis
# results via a Tcl heuristic, injecting them into OrfsInfo.arguments as .json.
orfs_arguments(
    name = "lb_32x128_auto_utilization",
    src = ":lb_32x128_synth",
    script = ":auto_utilization.tcl",
    tags = ["manual"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    extra_arguments = {"floorplan": [":lb_32x128_auto_utilization"]},
    last_stage = "floorplan",
    sources = LB_SOURCES,
    tags = ["manual"],
    variant = "auto_util",
    verilog_files = LB_VERILOG_FILES,
)

# Demonstrates the DSE/AutoTuner contract README.md documents: the script
# reports its objective by writing JSON to METRICS_OUT, which the caller
# names. cell_count.tcl errors out when METRICS_OUT is unset, so it is
# part of the contract rather than an option. It rides on extra_args
# rather than arguments= because the value has to name a declared output
# under $WORK_HOME, and only extra_args is shell-expanded -- a
# "$(WORK_HOME)/..." in arguments= reaches the script verbatim.
orfs_run(
    name = "cell_count",
    src = ":lb_32x128_floorplan",
    outs = [
        "cell_count_metrics.json",
        "test.txt",
    ],
    extra_args = "METRICS_OUT=$WORK_HOME/cell_count_metrics.json > $WORK_HOME/test.txt",
    script = ":cell_count.tcl",
)

# ci.yml runs `bazelisk test ... --build_tests_only`, so a target no test
# depends on is never built there. cell_count is such a target, and it
# silently stopped building when cell_count.tcl grew its METRICS_OUT
# requirement. Naming it in a build_test is what puts it back under CI.
build_test(
    name = "cell_count_build_test",
    targets = [":cell_count"],
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
    html = True,
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
            "macros": ["amalgam"],
            "sources": {
                "IO_CONSTRAINTS": [":L1MetadataArray_io-placement.tcl"],
                "SDC_FILE": [":constraints-top.sdc"],
            },
        },
        "base": {
            "macros": ["tag_array_64x184_generate_abstract"],
            "sources": {
                "IO_CONSTRAINTS": [":L1MetadataArray_io-placement.tcl"],
                "SDC_FILE": [":constraints-top.sdc"],
            },
        },
    },
    verilog_files = ["rtl/L1MetadataArray.sv"],
)

# Exercises the orfs_flow(html=True) plumbing end-to-end: builds the
# HTML timing report artifact (requires OpenROAD with web_save_report
# from PR #10087). Skipped by wildcard builds via "manual" tag on the
# underlying _gen targets. Tagged manual here too since it depends on
# an OpenROAD build that carries the PR.
build_test(
    name = "L1MetadataArray_html_build_test",
    tags = ["manual"],
    targets = [
        ":L1MetadataArray_synth_html_gen",
        ":L1MetadataArray_floorplan_html_gen",
        ":L1MetadataArray_cts_html_gen",
    ],
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

# Regression fixture for environment.bzl source_inputs(ctx) propagating
# the src target's OrfsDepInfo.files into the action input depset.
# dummy_extra.lef is attached to the floorplan stage's `data =`; the
# patch's job is to make it reach the chained place stage's action
# inputs as well. Without the patch the LEF is staged for floorplan
# only and the chained place stage sees a stale path for it in args.mk
# that is missing from the sandbox -- klayout / openroad fail errno=2
# on first read.
#
# Chained off the existing :Mul_synth target (cheapest available synth
# fixture). The synth stage builds OrfsDepInfo.files differently
# (verilog_files instead of ctx.files.data, see private/rules.bzl
# _yosys_impl) so the propagation we're testing only kicks in once
# the upstream stage is also _make_impl-based -- which is the case
# from floorplan onward.
orfs_floorplan(
    name = "src_propagation_floorplan",
    src = ":Mul_synth",
    arguments = {},
    data = [":dummy_extra.lef"],
    tags = ["manual"],
    variant = "src_propagation",
)

orfs_place(
    name = "src_propagation_place",
    src = ":src_propagation_floorplan",
    arguments = {},
    tags = ["manual"],
    variant = "src_propagation",
)

source_input_propagation_test(
    name = "src_data_propagation_test",
    expected_basename = "dummy_extra.lef",
    target_under_test = ":src_propagation_place",
)

# Unit tests for the stage variable filtering helpers (stages.bzl).
# Guards the generated-BUILD mechanism: that the generator in
# MODULE.bazel's patch_cmds agrees with the canonical BUILDs ORFS still
# ships, and that it behaves against a fixture tree. It reads the
# generator out of MODULE.bazel rather than keeping a copy, so the two
# cannot drift.
py_test(
    name = "orfs_recorded_builds_test",
    size = "small",
    srcs = ["orfs_recorded_builds_test.py"],
    data = ["//:orfs_design_builds.bzl"],
    main = "orfs_recorded_builds_test.py",
)

py_test(
    name = "orfs_flow_build_test",
    size = "small",
    srcs = ["orfs_flow_build_test.py"],
    data = ["//:orfs_source.bzl"],
    main = "orfs_flow_build_test.py",
)

py_test(
    name = "orfs_platforms_test",
    srcs = ["orfs_platforms_test.py"],
    data = [
        "//:MODULE.bazel",
        "//:orfs_source.bzl",
    ],
)

py_test(
    name = "orfs_design_builds_test",
    size = "small",
    srcs = ["orfs_design_builds_test.py"],
    data = [
        "//:orfs_design_builds.bzl",
        "//:orfs_source.bzl",
    ],
    main = "orfs_design_builds_test.py",
)

# ORFS tests we regression-test here, enumerated deliberately.
#
# `...` expands to the main repository only, so an @orfs test is invisible
# to `bazelisk test ...`. A test_suite is the idiomatic bridge: `...`
# expands suites into their members, so naming a test here is enough and
# CI needs no separate target list.
#
# This is a curated list, not "every ORFS test". ORFS is an immutable
# store of reference designs, scripts, PDKs and metadata; the knowledge of
# which of its tests are worth running under bazel lives here, and grows
# as features earn regression coverage.
#
# Adding one: the test must be a real target in @orfs and visible --
# test_suite membership is a dependency edge, unlike a command-line
# target, which is why design() makes flow targets public. Prefer the
# smallest design that exercises the feature; a full flow per entry is the
# cost.
#
#   asap7/gcd:gcd_test -- the smallest CI design (grt in ~50s). Runs the
#       flow and checks the design's own rules file, so it covers
#       everything from the module boundary down to metadata generation.
# ORFS designs whose flow this repository regression-tests, enumerated
# deliberately rather than swept up.
#
# These answer a different question from the "Load @orfs design packages"
# CI step, and the split is intentional. That step loads every design
# package -- 4135 targets, seconds -- and must never break, because DSL
# or rule-signature skew breaks every design at once; that is how the
# `blender` argument went unnoticed. These build and run a flow, and are
# allowed to break: an ORFS bump that upsets one design is a fix here,
# not an incident, because these designs exist for experiments rather
# than for tapeouts.
#
# So the list stays small and asap7-only, chosen for runtime rather than
# coverage. Each `<design>_test` runs the flow and compares metrics
# against the design's own rules-base.json.
#
# Add one only when a feature earns regression coverage, and be willing
# to drop one that turns out slow or noisy -- broad design coverage is
# explicitly not the deal. See docs/plans/orfs-as-file-store.md.
ORFS_TESTS = [
    # The smallest design in the flow, the one every example in the docs
    # uses, and SYNTH_USE_SYN=1 -- so it covers the OpenROAD-SYN path.
    "@orfs//flow/designs/asap7/gcd:gcd_test",
    # SYNTH_HDL_FRONTEND=slang, so this is what covers the yosys-slang
    # plugin path that orfs.default(yosys_plugins=...) wires up. Also
    # SYNTH_BLACKBOXES and VERILOG_TOP_PARAMS.
    "@orfs//flow/designs/asap7/uart:uart_test",
]

test_suite(
    name = "orfs_design_tests",
    tests = ORFS_TESTS + [":orfs_mock_alu_build_test"],
)

# mock-alu covers what neither design above reaches:
# OPENROAD_HIERARCHICAL=1, SWAP_ARITH_OPERATORS=1, and a config.mk that
# `include`s designs/src/mock-alu/defaults.mk -- an included makefile is
# a shape config_mk_parser has to resolve.
#
# It is a build_test rather than a member of ORFS_TESTS on purpose.
# `<design>_test` runs the flow *and* compares metrics against the
# design's rules-base.json, and at the current pin mock-alu misses one
# of 27 bounds by 0.9% -- finish__timing__setup__tns -18663.9 against
# -18500 -- with 0 DRCs and every other check passing. That is QoR drift
# from the OpenROAD bump measured against bounds tuned at the old pin,
# in a file that belongs to ORFS.
#
# Gating our CI on it would mean red on every tool bump until somebody
# re-tunes someone else's file. A build_test asks the question we
# actually want asked of this design -- does the flow still run -- and
# leaves the metric bounds to the repository that owns them.
build_test(
    name = "orfs_mock_alu_build_test",
    targets = ["@orfs//flow/designs/asap7/mock-alu:MockAlu_final"],
)

keep_modules_test_suite(name = "keep_modules_test")

work_home_test_suite(name = "work_home_test")

stages_filter_test_suite(name = "stages_filter_test")

# Test SYNTH_KEEP_MODULES: skip keep-hierarchy discovery, go straight to
# parallel partition synthesis with a pre-specified module list.
orfs_synth(
    name = "kept_modules_synth",
    arguments = {
        "SDC_FILE": "$(location :constraints-top.sdc)",
        "SYNTH_KEEP_MODULES": "adder counter",
    },
    data = [":constraints-top.sdc"],
    module_top = "kept_modules_top",
    verilog_files = ["rtl/kept_modules_top.v"],
)

build_test(
    name = "kept_modules_synth_test",
    targets = [":kept_modules_synth"],
)

# The other branch of parallel synthesis: SYNTH_HIERARCHICAL=1 with no
# SYNTH_KEEP_MODULES, so the kept modules are discovered by synth_keep.tcl
# at build time and each partition synthesizes from the global keep
# checkpoint. This is the path every ORFS hierarchical design without a
# pinned list takes (asap7/coralnpu, asap7/riscv32i, sky130hd/microwatt,
# ...); it had no in-repo test, and f3c5254 broke it unnoticed for three
# months -- every partition died with "per-module checkpoint missing".
# Two partitions over a three-module fixture: seconds of yosys.
orfs_synth(
    name = "discovered_modules_synth",
    arguments = {
        "SDC_FILE": "$(location :constraints-top.sdc)",
        "SYNTH_HIERARCHICAL": "1",
        "SYNTH_NUM_PARTITIONS": "2",
    },
    data = [":constraints-top.sdc"],
    module_top = "kept_modules_top",
    # Same module_top as kept_modules_synth; a distinct variant keeps
    # the two result trees from claiming the same output paths.
    variant = "discovered",
    verilog_files = ["rtl/kept_modules_top.v"],
)

build_test(
    name = "discovered_modules_synth_test",
    targets = [":discovered_modules_synth"],
)

filegroup(
    name = "discovered_modules_synth_netlist",
    srcs = [":discovered_modules_synth"],
    output_group = "1_2_yosys.v",
)

# Completion is not enough: prove the partitions produced the kept
# modules, so a regression to a flattened or empty merge is caught.
sh_test(
    name = "discovered_modules_netlist_test",
    size = "small",
    srcs = ["synth_discovery_netlist_test.sh"],
    args = [
        "$(location :discovered_modules_synth_netlist)",
        "adder",
        "counter",
        "kept_modules_top",
    ],
    data = [":discovered_modules_synth_netlist"],
)

# Lock the SDC/clock-period split on the serial synth path (Mul_synth):
# the expensive actions read only the extracted clock_period.txt; the raw
# SDC feeds only the cheap extraction and sdc-copy actions, so a
# period-preserving SDC edit never re-runs synthesis.
synth_action_inputs_test(
    name = "sdc_serial_clock_period_extraction_test",
    output_basename = "clock_period.txt",
    required_input_basenames = ["constraints-combinational.sdc"],
    target_under_test = ":Mul_synth",
)

synth_action_inputs_test(
    name = "sdc_serial_canonicalize_test",
    forbidden_input_basenames = ["constraints-combinational.sdc"],
    output_basename = "1_1_yosys_canonicalize.rtlil",
    required_input_basenames = ["clock_period.txt"],
    target_under_test = ":Mul_synth",
)

synth_action_inputs_test(
    name = "sdc_serial_do_yosys_test",
    forbidden_input_basenames = ["constraints-combinational.sdc"],
    output_basename = "1_2_yosys.v",
    required_input_basenames = [
        "1_1_yosys_canonicalize.rtlil",
        "clock_period.txt",
    ],
    target_under_test = ":Mul_synth",
)

synth_action_inputs_test(
    name = "sdc_serial_sdc_copy_test",
    output_basename = "1_2_yosys.sdc",
    required_input_basenames = ["constraints-combinational.sdc"],
    target_under_test = ":Mul_synth",
)

synth_action_inputs_test(
    name = "sdc_serial_odb_test",
    output_basename = "1_synth.odb",
    required_input_basenames = [
        "1_2_yosys.sdc",
        "1_2_yosys.v",
    ],
    target_under_test = ":Mul_synth",
)

# print-LIB_FILES is a pure make-variable expansion: config + platform
# includes only — it opens neither the RTLIL nor the SDC, so neither
# may re-run it.
synth_action_inputs_test(
    name = "sdc_serial_vars_test",
    forbidden_input_basenames = [
        "1_1_yosys_canonicalize.rtlil",
        "constraints-combinational.sdc",
    ],
    output_basename = "1_synth.vars",
    target_under_test = ":Mul_synth",
)

# Same split on the parallel/hierarchical path (kept_modules_synth).
synth_action_inputs_test(
    name = "sdc_parallel_partition_test",
    forbidden_input_basenames = ["constraints-top.sdc"],
    output_basename = "partition_top.v",
    required_input_basenames = ["clock_period.txt"],
    target_under_test = ":kept_modules_synth",
)

# Per-module canonicalize never sources synth_preamble.tcl, so it needs
# neither the raw SDC nor the extracted period.
synth_action_inputs_test(
    name = "sdc_parallel_module_canonicalize_test",
    forbidden_input_basenames = [
        "clock_period.txt",
        "constraints-top.sdc",
    ],
    output_basename = "partition_adder_canonical.rtlil",
    target_under_test = ":kept_modules_synth",
)

synth_action_inputs_test(
    name = "sdc_parallel_sdc_copy_test",
    output_basename = "1_2_yosys.sdc",
    required_input_basenames = ["constraints-top.sdc"],
    target_under_test = ":kept_modules_synth",
)

# The raw SDC is a synth-only concern: downstream stages consume the
# canonicalized 1_synth.sdc (write_sdc output) and must never see the
# raw SDC_FILE — otherwise every raw-SDC edit re-runs floorplan+.
synth_action_inputs_test(
    name = "sdc_isolated_to_synth_test",
    forbidden_input_basenames = ["constraints-combinational.sdc"],
    output_basename = "2_floorplan.odb",
    required_input_basenames = ["1_synth.sdc"],
    target_under_test = ":src_propagation_floorplan",
)

# Stage logs are timestamped (Elapsed/CPU/Peak-memory on every run), so
# they enter an orfs_run's inputs only via src_logs = True — a default
# log input re-ran every orfs_run whenever any upstream stage
# re-executed, byte-identical artifacts or not.
synth_action_inputs_test(
    name = "orfs_run_no_src_logs_by_default_test",
    forbidden_input_basenames = [
        "1_synth.log",
        "2_1_floorplan.log",
    ],
    output_basename = "lb_32x128_io-placement.tcl",
    target_under_test = ":lb_32x128_write_pin_placement",
)

synth_action_inputs_test(
    name = "orfs_run_src_logs_opt_in_test",
    output_basename = "ground_truth.json",
    required_input_basenames = ["5_1_grt.log"],
    target_under_test = "//test/estimation_ladder:extract_ground_truth",
)

# A stage's inputs carry only the macro .lib variant its args.mk
# references (orfs_additional_arguments use_pre_layout): floorplan/place
# take the pre-layout (ideal-clock) libs, later stages the post-layout
# ones. Both .lib variants share a basename and differ only in the
# variant directory, hence the path matching. Without the split, a
# macro re-characterization that touches one variant re-ran stages that
# only reference the other.
synth_action_inputs_test(
    name = "lib_pre_layout_inputs_floorplan_test",
    forbidden_input_path_contains = ["base/lb_32x128_typ.lib"],
    output_basename = "2_floorplan.odb",
    required_input_path_contains = ["pre_layout/lb_32x128_typ.lib"],
    target_under_test = ":lb_32x128_top_mock_hierarchy_floorplan",
)

synth_action_inputs_test(
    name = "lib_post_layout_inputs_abstract_test",
    forbidden_input_path_contains = ["pre_layout/lb_32x128_typ.lib"],
    output_basename = "lb_32x128_top.lef",
    required_input_path_contains = ["base/lb_32x128_typ.lib"],
    target_under_test = ":lb_32x128_top_mock_hierarchy_generate_abstract",
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
            "sources": {
                "IO_CONSTRAINTS": [":io-sram"],
            },
            "tags": ["manual"],
        },
    },
    sources = {
        "IO_CONSTRAINTS": [":io-sram"],
        "SDC_FILE": [":constraints-sram"],
    },
    sweep = {
        "base": {
            "sources": {
                "IO_CONSTRAINTS": [":regfile_128x65_io-placement.tcl"],
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
    sources = {
        "IO_CONSTRAINTS": [":io-sram"],
        "SDC_FILE": [":constraints-sram"],
    },
    stage = "cts",
    sweep = {
        "1": {
            "arguments": {
                "CORE_AREA": "1.026 1.080 3.672 6.210",
                "CORE_ASPECT_RATIO": "",
                "CORE_UTILIZATION": "",
                "DIE_AREA": "0 0 4.700 7.400",
                "PLACE_DENSITY": "0.65",
            },
            "previous_stage": {"floorplan": "lb_32x128_synth"},
            "sources": {
                "IO_CONSTRAINTS": [":lb_32x128_sweep_io-placement.tcl"],
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

# Same as gatelist_wc but using orfs_genrule -- exercises the rule's
# tools attr and select()-friendly srcs. Both srcs and outputs stay in
# target config; the orfs_genrule consumer hits the same action keys
# as orfs_run consumers of the same gatelist/spef pipeline.
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
    sources = LB_SOURCES,
    variant = "mock_openroad",
    verilog_files = LB_VERILOG_FILES,
)

# Exercise orfs_run's out_dir (tree-artifact output directory): the script
# decides at runtime what files land in $RUN_OUTPUT_DIR. Fast in CI via
# mock-openroad.
orfs_run(
    name = "run_out_dir_mock",
    src = ":lb_32x128_mock_openroad_floorplan",
    openroad = "//mock/openroad/src/bin:openroad",
    out_dir = "run_out_dir_mock_out",
    script = ":run_out_dir.tcl",
)

sh_test(
    name = "run_out_dir_test",
    srcs = ["run_out_dir_test.sh"],
    args = ["$(rootpath :run_out_dir_mock)"],
    data = [":run_out_dir_mock"],
)

# LOG_DIR names the log directory of the flow the src stage belongs to —
# where every stage's log and metrics json accumulates — not one derived
# from the consuming run's own package and variant. The two coincide only
# when the run is co-located with its src, so both cases are pinned: a run
# whose package differs from its src's (//test/log_dir_probe) found an
# empty LOG_DIR and left every src_logs consumer to hand-derive the path
# from an artifact it happened to know. A variant of its own is fine:
# LOG_DIR follows the src stage's FLOW_VARIANT, not this target's.
#
# The squashed cts flow is the src because it accumulates floorplan,
# place and cts in one directory, so the expected set spans stages.
orfs_run(
    name = "log_dir_probe_mock",
    src = ":lb_32x128_squashed_cts",
    outs = ["log_dir_probe.txt"],
    arguments = {
        "OUTPUT": "$(location log_dir_probe.txt)",
    },
    openroad = "//mock/openroad/src/bin:openroad",
    script = ":log_dir_probe.tcl",
    src_logs = True,
    variant = "log_dir_probe",
)

sh_test(
    name = "log_dir_probe_test",
    srcs = ["log_dir_probe_test.sh"],
    args = [
        "$(rootpath :log_dir_probe_expected.txt)",
        "$(rootpath :log_dir_probe.txt)",
    ],
    data = [
        ":log_dir_probe.txt",
        ":log_dir_probe_expected.txt",
    ],
)

exports_files(
    [
        "log_dir_probe.tcl",
        "log_dir_probe_expected.txt",
        "log_dir_probe_test.sh",
    ],
    visibility = ["//test:__subpackages__"],
)

alias(
    name = "log_dir_probe_src",
    actual = ":lb_32x128_squashed_cts",
    visibility = ["//test:__subpackages__"],
)

# fork/join smoke on real OpenROAD (see fork/fork.tcl): a nested tree walk
# after load_design writing one JSON per leaf into out_dir, with an OpenSTA
# query in every forked child and a deliberate failing leaf.
orfs_run(
    name = "fork_smoke",
    src = ":lb_32x128_floorplan",
    openroad = "@openroad//:openroad",
    out_dir = "fork_smoke_out",
    script = ":fork_smoke.tcl",
    tags = ["manual"],
)

build_test(
    name = "fork_smoke_test",
    tags = ["manual"],
    targets = [":fork_smoke"],
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
    sources = LB_SOURCES,
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
    sources = LB_SOURCES,
    squash = True,
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
    sources = LB_SOURCES,
    squash = True,
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
    deps = ["@bazel-orfs-dev-pip//pytest"],
)

py_test(
    name = "tcl_interpreter_test",
    srcs = [
        "//mock/openroad/src/bin:tcl_interpreter.py",
        "//mock/openroad/src/bin:tcl_interpreter_test.py",
    ],
    imports = ["."],
    deps = ["@bazel-orfs-dev-pip//pytest"],
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
    deps = ["@bazel-orfs-dev-pip//pytest"],
)

# --- Mock-openroad build tests: fast validation of .bzl rule logic ---

build_test(
    name = "mock_openroad_floorplan_build_test",
    targets = [":lb_32x128_mock_openroad_floorplan"],
)

# --- quick_pins flag wiring test ---
#
# Verifies orfs_flow(quick_pins=True) injects the two TCL hooks as data deps
# on the place stage:
#   PRE_GLOBAL_PLACE_SKIP_IO_TCL -> @bazel-orfs//:quick_pins.tcl
#   FOOTPRINT_TCL                -> @bazel-orfs//:quick_pins_footprint_stub.tcl
# Pure analysis-time check; no OpenROAD invocation.
# buildifier: disable=duplicated-name
orfs_flow(
    name = "lb_32x128",
    arguments = LB_ARGS,
    last_stage = "place",
    openroad = "//mock/openroad/src/bin:openroad",
    previous_stage = {"floorplan": ":lb_32x128_synth"},
    quick_pins = True,
    sources = LB_SOURCES,
    variant = "quick_pins",
    verilog_files = LB_VERILOG_FILES,
)

quick_pins_data_dep_test(
    name = "quick_pins_place_data_dep_test",
    expected_basenames = ["quick_pins.tcl"],
    target = ":lb_32x128_quick_pins_place",
)

quick_pins_data_dep_test(
    name = "quick_pins_floorplan_data_dep_test",
    expected_basenames = ["quick_pins_footprint_stub.tcl"],
    target = ":lb_32x128_quick_pins_floorplan",
)

# Regression test for the synth → generate_metadata data-dep wiring in
# private/flow.bzl. Without it, genMetrics.py reads 1_2_yosys.v from a
# sandbox path that does not exist and synth__netlist__hash lands as
# "N/A". The metadata target's runfiles must carry the post-ABC netlist.
quick_pins_data_dep_test(
    name = "generate_metadata_synth_data_dep_test",
    expected_basenames = ["1_2_yosys.v"],
    target = ":regfile_128x65_generate_metadata",
)

build_test(
    name = "quick_pins_place_build_test",
    targets = [":lb_32x128_quick_pins_place"],
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
    sources = LB_SOURCES,
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
    sources = LB_SOURCES,
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
    sources = LB_SOURCES | {
        "ADDITIONAL_LEFS": [":dummy_extra.lef"],
    },
    variant = "mock_hierarchy_merge",
    verilog_files = ["rtl/lb_32x128_top.v"],
)

build_test(
    name = "mock_hierarchy_merge_build_test",
    targets = [":lb_32x128_top_mock_hierarchy_merge_generate_abstract"],
)

# Fixture for the macro-GDS input-scoping tests: a macro carrying a
# .gds, consumed by a full flow. Never built (manual) — the
# analysistests below only inspect its action graph.
write_file(
    name = "gds_scope_dummy_gds",
    out = "gds_scope_dummy.gds",
    content = ["dummy"],
)

orfs_macro(
    name = "gds_scope_macro",
    gds = ":gds_scope_dummy_gds",
    lef = ":lb_32x128_mock_abstract_generate_abstract",
    lib = ":lb_32x128_mock_abstract_generate_abstract",
    module_top = "lb_32x128",
)

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
    macros = ["gds_scope_macro"],
    sources = LB_SOURCES,
    tags = ["manual"],
    variant = "gds_scope",
    verilog_files = ["rtl/lb_32x128_top.v"],
)

# A macro's .gds is read only by the GDS-emitting steps: synthesis and
# the PnR stages before final must not carry it (a macro .gds change
# with stable .lef/.lib used to re-run the parent's whole chain), while
# the final stage's klayout wrap keeps it.
synth_action_inputs_test(
    name = "macro_gds_synth_excluded_test",
    forbidden_input_basenames = ["gds_scope_dummy.gds"],
    output_basename = "1_2_yosys.v",
    target_under_test = ":lb_32x128_top_gds_scope_synth",
)

synth_action_inputs_test(
    name = "macro_gds_floorplan_excluded_test",
    forbidden_input_basenames = ["gds_scope_dummy.gds"],
    output_basename = "2_floorplan.odb",
    target_under_test = ":lb_32x128_top_gds_scope_floorplan",
)

synth_action_inputs_test(
    name = "macro_gds_final_included_test",
    output_basename = "6_final.odb",
    required_input_basenames = ["gds_scope_dummy.gds"],
    target_under_test = ":lb_32x128_top_gds_scope_final",
)

# Upstream metrics .json / report files feed only genMetrics.py: the
# PnR stage actions never open them, so they are declared by the
# metadata stages and dropped everywhere else (the jsons are supposed
# to be byte-stable, but OpenROAD is not trusted on that — consumers
# state the dependency, nobody is fed it for convenience).
synth_action_inputs_test(
    name = "metrics_jsons_not_in_cts_test",
    # 2_1_floorplan.json rides only LoggingInfo; 2_floorplan_final.rpt
    # and 2_floorplan.odb used to arrive one hop past their readers via
    # the src's OrfsDepInfo.files re-feeding the previous stage's whole
    # DefaultInfo (cts legitimately reads only place's own results).
    forbidden_input_basenames = [
        "1_synth.json",
        "2_1_floorplan.json",
        "2_floorplan.odb",
        "2_floorplan_final.rpt",
    ],
    output_basename = "4_cts.odb",
    target_under_test = ":lb_32x128_cts",
)

# A stage's action inputs stop one hop back: place reads floorplan's
# results (and the deliberately forwarded canonicalize RTLIL), never
# synth's netlist or ODB — those reached place only through floorplan's
# OrfsDepInfo.files re-feeding synth's whole DefaultInfo.
synth_action_inputs_test(
    name = "no_n_minus_2_inputs_place_test",
    forbidden_input_basenames = [
        "1_2_yosys.v",
        "1_synth.odb",
        "1_synth.vars",
    ],
    output_basename = "3_place.odb",
    required_input_basenames = ["2_floorplan.odb"],
    target_under_test = ":lb_32x128_top_gds_scope_place",
)

# 1_synth.vars left synth's DefaultInfo.files (no stage reads it) but
# MUST stay in the runfiles: odb-debug-style tooling recovers LIB_FILES
# by globbing *.vars there and fails silently without it.
runfiles_contents_test(
    name = "synth_vars_in_runfiles_test",
    required_basenames = ["1_synth.vars"],
    target_under_test = ":Mul_synth",
)

synth_action_inputs_test(
    name = "synth_vars_not_in_floorplan_test",
    forbidden_input_basenames = ["1_synth.vars"],
    output_basename = "2_floorplan.odb",
    target_under_test = ":lb_32x128_top_gds_scope_floorplan",
)

# Pins the intended consumer so an input-hygiene refactor can't
# silently starve genMetrics.py (it reads stage logs AND jsons).
synth_action_inputs_test(
    name = "metrics_jsons_reach_metadata_test",
    output_basename = "metadata.json",
    required_input_basenames = [
        "1_synth.log",
        "2_1_floorplan.json",
    ],
    target_under_test = ":lb_32x128_top_gds_scope_generate_metadata",
)

# Mock sweep test: tests orfs_sweep with macros + openroad override.
# Uses mock-openroad for all stages. The sweep's "base" variant uses
# lb_32x128_mock_abstract as a macro (hierarchical design).
orfs_sweep(
    name = "mock_sweep_lb",
    abstract_stage = "cts",
    arguments = LB_ARGS,
    openroad = "//mock/openroad/src/bin:openroad",
    sources = LB_SOURCES,
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
    sources = LB_SOURCES,
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
    sources = LB_SOURCES,
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
    sources = {
        "IO_CONSTRAINTS": [":io-sram"],
        "SDC_FILE": [":constraints-sram"],
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
    sources = LB_SOURCES,
    variant = "mock_full_abstract",
    verilog_files = LB_VERILOG_FILES,
)

# Verify that orfs_macro forwards lib_pre_layout from the inner
# orfs_abstract. This is a bare orfs_macro wrapping the mock abstract
# (which has abstract_stage="cts", past "place", so it emits a
# pre-layout abstract). The test asserts lib_pre_layout is non-None.
orfs_macro(
    name = "lb_32x128_mock_macro_wrapper",
    lef = ":lb_32x128_mock_full_abstract_generate_abstract",
    lib = ":lb_32x128_mock_full_abstract_generate_abstract",
    module_top = "lb_32x128",
)

lib_pre_layout_test(
    name = "lib_pre_layout_macro_test",
    target = ":lb_32x128_mock_macro_wrapper",
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
    sources = LB_SOURCES,
    variant = "mock_full_hierarchy",
    verilog_files = ["rtl/lb_32x128_top.v"],
    yosys = "//mock/yosys/src/bin:yosys",
)

# --- orfs_run(deps = True): the reproducer companions on a run target ---
# Fully mock (mock openroad + mock yosys), so this costs no real tool build.

orfs_run(
    name = "lb_32x128_mock_run_with_deps",
    src = ":lb_32x128_mock_floorplan",
    outs = ["lb_32x128_mock_run_with_deps.yaml"],
    arguments = {
        "OUTPUT": "lb_32x128_mock_run_with_deps.yaml",
    },
    script = ":report_named.tcl",
    tags = ["manual"],
    deps = True,
)

# The deployed reproducer carries a usable config.mk, same as a stage's.
sh_test(
    name = "deps_deploy_run_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_mock_run_with_deps_deps_tar.tar.gz)",
        "config_contains",
        "DESIGN_NAME",
    ],
    data = [":lb_32x128_mock_run_with_deps_deps_tar.tar.gz"],
)

deps_output_group_test(
    name = "deps_output_group_run_test",
    target = ":lb_32x128_mock_run_with_deps_deps_tar",
)

# --- Deps deploy tests: verify end-to-end deploy workflow ---
# These replace deps_integration_test.sh with Bazel-native tests
# that receive pre-built tarballs — no nested bazelisk calls.

sh_test(
    name = "deps_deploy_synth_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_mock_synth_deps_tar.tar.gz)",
        "dir_exists",
    ],
    data = [":lb_32x128_mock_synth_deps_tar.tar.gz"],
)

sh_test(
    name = "deps_deploy_floorplan_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_mock_floorplan_deps_tar.tar.gz)",
        "print_flow_home",
    ],
    data = [":lb_32x128_mock_floorplan_deps_tar.tar.gz"],
)

sh_test(
    name = "deps_deploy_real_floorplan_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :tag_array_64x184_mock_floorplan_deps_tar.tar.gz)",
        "print_flow_home",
    ],
    data = [":tag_array_64x184_mock_floorplan_deps_tar.tar.gz"],
)

sh_test(
    name = "deps_deploy_hierarchy_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_top_mock_full_hierarchy_floorplan_deps_tar.tar.gz)",
        "config_contains",
        "ADDITIONAL_LEFS",
    ],
    data = [":lb_32x128_top_mock_full_hierarchy_floorplan_deps_tar.tar.gz"],
)

sh_test(
    name = "deps_deploy_openroad_exe_env_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :lb_32x128_mock_floorplan_deps_tar.tar.gz)",
        "openroad_exe_env",
    ],
    data = [":lb_32x128_mock_floorplan_deps_tar.tar.gz"],
)

sh_test(
    name = "deps_deploy_make_passthrough_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :tag_array_64x184_mock_floorplan_deps_tar.tar.gz)",
        "make_passthrough",
    ],
    data = [":tag_array_64x184_mock_floorplan_deps_tar.tar.gz"],
)

sh_test(
    name = "deps_deploy_run_substep_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :tag_array_64x184_mock_floorplan_deps_tar.tar.gz)",
        "run_substep",
    ],
    data = [":tag_array_64x184_mock_floorplan_deps_tar.tar.gz"],
)

# --- Deps pkg_tar tests: verify on-demand deps deployment ---

# Test deps tarball on synth (yosys) stage
deps_output_group_test(
    name = "deps_output_group_synth_test",
    target = ":lb_32x128_synth_deps_tar",
)

# Test deps tarball on floorplan (openroad) stage
deps_output_group_test(
    name = "deps_output_group_floorplan_test",
    target = ":lb_32x128_mock_openroad_floorplan_deps_tar",
)

# Test deps tarball on squashed flow stage
deps_output_group_test(
    name = "deps_output_group_squashed_test",
    target = ":lb_32x128_squashed_final_final_deps_tar",
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
    sources = LB_SOURCES,
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
    target = ":lb_32x128_substeps_floorplan_deps_tar",
)

# --- BCR yosys module layout tests ---
# Smoke tests over the BCR yosys module's layout (plugin hdrs, share
# tree): glob + analysis only, no compilation. A yosys bump that
# reorganizes the module fails here first. BCR yosys is already
# fetched for @yosys//:yosys_share.

build_test(
    name = "yosys_hdrs_build_test",
    targets = ["@yosys//:hdrs"],
)

build_test(
    name = "yosys_share_build_test",
    targets = ["@yosys//:yosys_share"],
)

# Guards the {*}-expansion of SYNTH_RETIME_MODULES in synth.tcl. Without
# `{*}`, `select $::env(SYNTH_RETIME_MODULES)` passes a space-separated value
# as a single bogus pattern and silently disables retime across every named
# module — see commit message and synth_retime_select_test.tcl for details.
# Fast: drives yosys directly on a 4-module fixture, no ORFS flow.
sh_test(
    name = "synth_retime_select_test",
    srcs = ["synth_retime_select_test.sh"],
    args = [
        "$(location @yosys//:yosys)",
        "$(location :synth_retime_select_test.tcl)",
        "$(location :synth_retime_select_test.v)",
        "$(location //:synth.tcl)",
    ],
    data = [
        ":synth_retime_select_test.tcl",
        ":synth_retime_select_test.v",
        "//:synth.tcl",
        "@yosys",
    ],
)

# Guards the SYNTH_KEEP_MODULES typo-check in synth.tcl / synth_keep.tcl.
# Pre-fix: `select "$mod" "$mod\\$*"` silently no-matched on a misspelled name,
# so a typo in SYNTH_KEEP_MODULES dropped keep_hierarchy without complaint.
# Post-fix: walk via `catch {rtlil::set_attr -mod $module keep_hierarchy 1}`,
# accumulate missing names, error at end. Partition synthesis (SYNTH_BLACKBOXES)
# skips the strict check. Fast: drives yosys directly on a 4-module fixture.
sh_test(
    name = "synth_keep_modules_check_test",
    srcs = ["synth_keep_modules_check_test.sh"],
    args = [
        "$(location @yosys//:yosys)",
        "$(location :synth_keep_modules_check_test.tcl)",
        "$(location :synth_keep_modules_check_test.v)",
        "$(location //:synth.tcl)",
        "$(location //:synth_keep.tcl)",
    ],
    data = [
        ":synth_keep_modules_check_test.tcl",
        ":synth_keep_modules_check_test.v",
        "//:synth.tcl",
        "//:synth_keep.tcl",
        "@yosys",
    ],
)

orfs_variables(
    name = "my_variables",
    arguments = {
        "MY_CUSTOM_VAR": "42",
    },
)

orfs_run(
    name = "my_run_test",
    src = ":lb_32x128_synth",
    outs = ["my_run_test.txt"],
    arguments = {
        "OUTPUT": "$(location :my_run_test.txt)",
    },
    extra_arguments = [":my_variables"],
    script = "write_my_var.tcl",
)

sh_test(
    name = "extra_arguments_test",
    srcs = ["verify_my_var.sh"],
    args = ["$(location :my_run_test.txt)"],
    data = [":my_run_test.txt"],
)

write_file(
    name = "dump_floorplan_vars_tcl",
    out = "dump_floorplan_vars.tcl",
    content = ["""
set out_file $env(OUT_vars_txt)
set fp [open $out_file w]
foreach var {CORE_UTILIZATION CORE_MARGIN PLACE_DENSITY} {
    if {[info exists env($var)]} {
        puts $fp "$var=$env($var)"
    } else {
        puts $fp "$var=MISSING"
    }
}
close $fp
"""],
)

orfs_run(
    name = "verify_synth_propagated_vars",
    src = ":lb_32x128_shared_synth_floorplan",
    outs = ["propagated_vars.txt"],
    arguments = {
        "OUT_vars_txt": "$(location :propagated_vars.txt)",
    },
    script = ":dump_floorplan_vars_tcl",
)

sh_test(
    name = "orfs_run_info_propagation_test",
    srcs = ["verify_orfs_run_vars.sh"],
    args = ["$(location :propagated_vars.txt)"],
    data = [":propagated_vars.txt"],
)

orfs_run_executable(
    name = "mock_tuner_executable",
    src = ":lb_32x128_floorplan",
    script = ":cell_count.tcl",
    tags = ["manual"],
)

py_test(
    name = "run_executable_test",
    srcs = ["run_executable_test.py"],
    data = [
        ":mock_tuner_executable",
        ":run_executable_custom_cmd",
        ":run_executable_with_args",
    ],
)

# orfs_run_executable(deps = True): the executable is deployable, so a bug
# hit in a tight-loop run can be handed over as a self-contained reproducer.
orfs_run_executable(
    name = "mock_tuner_executable_with_deps",
    src = ":lb_32x128_mock_floorplan",
    script = ":cell_count.tcl",
    tags = ["manual"],
    deps = True,
)

deps_output_group_test(
    name = "deps_output_group_run_executable_test",
    target = ":mock_tuner_executable_with_deps_deps_tar",
)

sh_test(
    name = "deps_deploy_run_executable_test",
    srcs = ["deps_deploy_test.sh"],
    args = [
        "$(location :mock_tuner_executable_with_deps_deps_tar.tar.gz)",
        "config_contains",
        "DESIGN_NAME",
    ],
    data = [":mock_tuner_executable_with_deps_deps_tar.tar.gz"],
)

orfs_run_executable(
    name = "run_executable_with_args",
    src = ":lb_32x128_floorplan",
    arguments = {"PLACE_DENSITY": "0.10"},
    script = ":cell_count.tcl",
    tags = ["manual"],
)

orfs_run_executable(
    name = "run_executable_custom_cmd",
    src = ":lb_32x128_floorplan",
    cmd = "print-PLACE_DENSITY",
    script = ":cell_count.tcl",
    tags = ["manual"],
)

write_file(
    name = "test_source_1",
    out = "test_source_1.txt",
    content = ["test_source_content"],
)

write_file(
    name = "test_source_2",
    out = "test_source_2.txt",
    content = ["second_source_content"],
)

write_file(
    name = "dump_sources_tcl",
    out = "dump_sources.tcl",
    content = ["""
set fp [open $::env(OUT_vars_txt) w]
set fd1 [open $::env(TEST_SOURCE_1) r]
puts $fp [read $fd1]
close $fd1
foreach src $::env(TEST_SOURCES) {
    set fdn [open $src r]
    puts $fp [read $fdn]
    close $fdn
}
close $fp
"""],
)

orfs_run(
    name = "test_orfs_run_sources",
    src = ":lb_32x128_synth",
    outs = ["test_orfs_run_sources.txt"],
    arguments = {
        "OUT_vars_txt": "$(location :test_orfs_run_sources.txt)",
    },
    script = ":dump_sources_tcl",
    sources = {
        "TEST_SOURCE_1": ":test_source_1",
        "TEST_SOURCES": [
            ":test_source_1",
            ":test_source_2",
        ],
    },
)

sh_test(
    name = "orfs_run_sources_test",
    srcs = ["verify_orfs_run_sources.sh"],
    args = ["$(location :test_orfs_run_sources.txt)"],
    data = [":test_orfs_run_sources.txt"],
)

orfs_test(
    name = "test_orfs_test_sources",
    src = ":lb_32x128_mock_openroad_floorplan",
    arguments = {
        "SCRIPT": "$(location :verify_orfs_test_sources.tcl)",
    },
    cmd = "run",
    data = [":verify_orfs_test_sources.tcl"],
    openroad = "//mock/openroad/src/bin:openroad",
    sources = {
        "TEST_SOURCE_1": ":test_source_1",
        "TEST_SOURCES": [
            ":test_source_1",
            ":test_source_2",
        ],
    },
)

orfs_test(
    name = "test_leak_single_stage",
    src = ":lb_32x128_place",
    cmd = "run",
    script = ":verify_no_leak.tcl",
    stages = ["synth"],
)

orfs_test(
    name = "test_leak_two_stages",
    src = ":lb_32x128_place",
    cmd = "run",
    script = ":verify_no_leak.tcl",
    stages = [
        "synth",
        "floorplan",
    ],
)

orfs_test(
    name = "test_leak_empty_stages",
    src = ":lb_32x128_place",
    cmd = "run",
    script = ":verify_leak.tcl",
    stages = [],
)

orfs_test(
    name = "test_platform_not_filtered",
    src = ":lb_32x128_place",
    cmd = "run",
    script = ":verify_platform.tcl",
)

orfs_test(
    name = "test_macro_synth",
    src = ":lb_32x128_top_synth",
    cmd = "run",
    openroad = "//mock/openroad/src/bin:openroad",
    script = ":verify_macro_collateral.tcl",
    stages = ["synth"],
    yosys = "//mock/yosys/src/bin:yosys",
)

orfs_test(
    name = "test_macro_floorplan",
    src = ":lb_32x128_top_floorplan",
    cmd = "run",
    openroad = "//mock/openroad/src/bin:openroad",
    script = ":verify_macro_collateral.tcl",
    stages = ["floorplan"],
    yosys = "//mock/yosys/src/bin:yosys",
)

# The <flow>_estimate report (docs/estimate.md): generated for every
# flow with a floorplan stage. Assert the JSON exists and carries the
# fields the differential protocol reads.
sh_test(
    name = "lb_32x128_estimate_test",
    srcs = ["estimate_test.sh"],
    args = ["$(rootpath :lb_32x128_estimate.json)"],
    data = [":lb_32x128_estimate.json"],
)
