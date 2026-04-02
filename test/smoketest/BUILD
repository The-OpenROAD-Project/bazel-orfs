"""Multi-PDK smoke tests: verify the full ORFS flow completes for all supported PDKs."""

load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("//:openroad.bzl", "orfs_flow")

PDKS = [
    "asap7",
    "gf180",
    "nangate45",
    "sky130hd",
    "sky130hs",
    "ihp-sg13g2",
]

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

# Full-flow smoke tests: these need real OpenROAD to produce valid metrics.
# Tagged manual — run explicitly when real tools are configured.
[orfs_flow(
    name = "lb_32x128_{}".format(pdk),
    arguments = FAST_SETTINGS | {
        "CORE_UTILIZATION": "3",
        "PLACE_DENSITY": "0.40",
    },
    pdk = "@orfs//flow:" + pdk,
    sources = {
        "SDC_FILE": ["//test:constraints-sram-sky130hd.sdc"],
    },
    tags = ["manual"],
    top = "lb_32x128",
    verilog_files = ["//test:mock/lb_32x128.sv"],
    visibility = ["//:__subpackages__"],
) for pdk in PDKS]

[build_test(
    name = "lb_32x128_{}_build_test".format(pdk),
    tags = ["manual"],
    targets = [":lb_32x128_{}_generate_abstract".format(pdk)],
) for pdk in PDKS]
