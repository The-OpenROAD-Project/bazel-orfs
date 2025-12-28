load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@rules_python//python:defs.bzl", "py_binary")

# Export TCL scripts for PPA extraction and DSE SDC
exports_files([
    "extract_timing.tcl",
    "extract_ppa.tcl",
    "constraints-dse.sdc",
])

# DSE-specific flow configuration with tighter constraints
orfs_flow(
    name = "lb_32x128",
    abstract_stage = "cts",
    arguments = {
        # Tight timing constraints for meaningful DSE
        "CORE_ASPECT_RATIO": "0.5",
        "CORE_UTILIZATION": "50",  # Higher utilization
        "PLACE_DENSITY": "0.20",
        "PLACE_PINS_ARGS": "-min_distance 1 -min_distance_in_tracks",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
        # Enable timing-driven optimization for DSE
        "GPL_TIMING_DRIVEN": "1",  # Enable timing-driven placement
        "SKIP_CTS_REPAIR_TIMING": "0",  # Enable CTS timing repair
        # Other fast settings
        "FILL_CELLS": "",
        "GND_NETS_VOLTAGES": "",
        "GPL_ROUTABILITY_DRIVEN": "0",
        "PWR_NETS_VOLTAGES": "",
        "REMOVE_ABC_BUFFERS": "1",
        "SKIP_INCREMENTAL_REPAIR": "1",
        "SKIP_REPORT_METRICS": "1",
        "TAPCELL_TCL": "",
    },
    sources = {
        "SDC_FILE": [":constraints-dse.sdc"],
        "IO_CONSTRAINTS": ["//:io-sram"],
    },
    tags = ["manual"],
    verilog_files = ["//:test/mock/lb_32x128.sv"],
)

# Extract timing information from CTS
orfs_run(
    name = "lb_32x128_timing",
    src = ":lb_32x128_cts",
    outs = ["lb_32x128_timing.txt"],
    arguments = {"OUTFILE": "$(location lb_32x128_timing.txt)"},
    script = ":extract_timing.tcl",
)

# Extract PPA (Performance, Power, Area) metrics from CTS
orfs_run(
    name = "lb_32x128_ppa",
    src = ":lb_32x128_cts",
    outs = ["lb_32x128_ppa.txt"],
    arguments = {"OUTFILE": "$(location lb_32x128_ppa.txt)"},
    script = ":extract_ppa.tcl",
)

# Main DSE optimizer: Find optimal CORE_UTILIZATION and PLACE_DENSITY
py_binary(
    name = "run",
    srcs = ["optimize_dse.py"],
    main = "optimize_dse.py",
    tags = ["manual"],
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-pip//matplotlib",
        "@bazel-orfs-pip//numpy",
        "@bazel-orfs-pip//optuna",
    ],
)
