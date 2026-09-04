# Examples, not tests.
#
# This package shows the idiomatic way to write a bazel-orfs flow: one
# orfs_flow() per design, RTL and constraints next to it, nothing shared
# with test fixtures. CI builds it (see the build_test at the bottom) so
# it can never rot, but it is written to be read first and run second:
# when clarity and coverage pull in different directions, clarity wins
# here and the coverage goes in //test.
load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("//:openroad.bzl", "orfs_flow")

# Skip the slow, sign-off-oriented parts of the flow. Every setting here
# is an ORFS variable; drop this dict for a real tapeout-grade run.
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

# Creates //examples:mac_synth, _floorplan, _place, _cts, _grt, _route and
# _final, plus //examples:mac_generate_abstract. Each stage target is a
# `bazelisk run` entry point with a gui_<stage> argument:
#
#   bazelisk run //examples:mac_final gui_final
orfs_flow(
    name = "mac",
    arguments = FAST_SETTINGS | {
        "CORE_UTILIZATION": "40",
        "PLACE_DENSITY": "0.65",
    },
    sources = {
        "SDC_FILE": [":constraints.sdc"],
    },
    verilog_files = ["mac.v"],
)

# Keeps the example building in CI. `bazelisk test ...` only builds what a
# test depends on, so without this the example would be invisible to CI.
build_test(
    name = "mac_build_test",
    targets = [":mac_final"],
)
