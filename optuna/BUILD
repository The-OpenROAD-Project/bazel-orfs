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
    name = "mock-cpu",
    abstract_stage = "cts",
    arguments = {
        "VERILOG_TOP_PARAMS": "NUM_CORES 2 PIPELINE_DEPTH 4 WORK_PER_STAGE 8",
        "CORE_ASPECT_RATIO": "0.5",
        "CORE_UTILIZATION": "50",  # Higher utilization
        "PLACE_DENSITY": "0.20",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
        # Tight timing constraints for meaningful DSE
        "ABC_CLOCK_PERIOD_IN_PS": "1000",
        # Synthesis
        "SYNTH_HDL_FRONTEND": "slang",
        # Speed up, we don't care about exact or timing results,
        # we'll still get roughly the RTL parameterization and
        # builds will be faster.
        "GPL_TIMING_DRIVEN": "0",
        "GPL_ROUTABILITY_DRIVEN": "0",
        # Other fast settings
        "SKIP_CTS_REPAIR_TIMING": "0",  # Enable CTS timing repair
        "FILL_CELLS": "",
        "GND_NETS_VOLTAGES": "",
        "PWR_NETS_VOLTAGES": "",
        "SKIP_INCREMENTAL_REPAIR": "1",
        "SKIP_REPORT_METRICS": "1",
        "TAPCELL_TCL": "",
        "TNS_END_PERCENT": "0",
    },
    sources = {
        "SDC_FILE": [":constraints-dse.sdc"],
    },
    tags = ["manual"],
    top = "mock_cpu",
    verilog_files = [":mock-cpu.sv"],
)

# Extract PPA (Performance, Power, Area) metrics from CTS
orfs_run(
    name = "mock-cpu_ppa",
    src = ":mock-cpu_synth",
    outs = ["mock-cpu_ppa.txt"],
    arguments = {"OUTFILE": "$(location mock-cpu_ppa.txt)"},
    script = ":extract_ppa.tcl",
)

# Main DSE optimizer: Find optimal CORE_UTILIZATION and PLACE_DENSITY
py_binary(
    name = "run",
    srcs = ["optimize_dse.py", "plot_results.py"],
    main = "optimize_dse.py",
    tags = ["manual"],
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-pip//matplotlib",
        "@bazel-orfs-pip//numpy",
        "@bazel-orfs-pip//optuna",
        "@bazel-orfs-pip//pandas",
        "@bazel-orfs-pip//plotly",
        "@bazel-orfs-pip//kaleido",
    ],
)
