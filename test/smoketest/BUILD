"""Multi-PDK smoke tests: verify the full ORFS flow completes for all supported PDKs."""

load("//:openroad.bzl", "orfs_flow")

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

[orfs_flow(
    name = "lb_32x128_{}".format(pdk),
    arguments = FAST_SETTINGS | {
        "CORE_UTILIZATION": "3",
        "PLACE_DENSITY": "0.40",
    },
    pdk = "@docker_orfs//:" + pdk,
    sources = {
        "SDC_FILE": ["//test:constraints-sram-sky130hd.sdc"],
    },
    top = "lb_32x128",
    verilog_files = ["//test:mock/lb_32x128.sv"],
    visibility = ["//:__subpackages__"],
) for pdk in [
    "asap7",
    "nangate45",
    "sky130hd",
    "ihp-sg13g2",
]]
