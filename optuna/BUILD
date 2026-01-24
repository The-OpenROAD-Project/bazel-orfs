load("@bazel-orfs//:openroad.bzl", "orfs_flow", "orfs_run")
load("@bazel_skylib//rules:common_settings.bzl", "string_flag")
load("@rules_python//python:defs.bzl", "py_binary")

# A balance between batch size/parallelism and frequency of
# feeding posteriors into the Bayesian optimizer.
N = 8

# Rungs from fastest least accurate to slowest most accurate builds.
STAGES = [
    "synth",
    "place",
    "grt",
]

[string_flag(
    name = "density{}".format(i),
    build_setting_default = "50",
) for i in range(N)]

[string_flag(
    name = "utilization{}".format(i),
    build_setting_default = "47",
) for i in range(N)]

[string_flag(
    name = "params{}".format(i),
    build_setting_default = "",
) for i in range(N)]

# Export TCL scripts for PPA extraction and DSE SDC
exports_files([
    "extract_timing.tcl",
    "extract_ppa.tcl",
    "constraints-dse.sdc",
])

# DSE-specific flow configuration with tighter constraints
[orfs_flow(
    name = "mock-cpu",
    abstract_stage = STAGES[-1],
    arguments = {
        # Timing somewhat close to what we're getting
        "ABC_CLOCK_PERIOD_IN_PS": "1000",
        # Synthesis
        "SYNTH_HDL_FRONTEND": "slang",
        # Not used, just slows things down
        "SKIP_REPORT_METRICS": "1",
        # repair only worst, only if we actually want to close timing do we
        # want to run repair on all endpoints
        "TNS_END_PERCENT": "0",
    },
    settings = {
        "CORE_UTILIZATION": ":utilization{}".format(i),
        "PLACE_DENSITY": ":density{}".format(i),
        "VERILOG_TOP_PARAMS": ":params{}".format(i),
    },
    sources = {
        "SDC_FILE": [":constraints-dse.sdc"],
    },
    tags = ["manual"],
    top = "mock_cpu",
    variant = "{}".format(i),
    verilog_files = [":mock-cpu.sv"],
) for i in range(N)]

# Extract PPA (Performance, Power, Area) metrics from CTS
[
    orfs_run(
        name = "mock-cpu_{}_{}_ppa".format(i, stage),
        src = ":mock-cpu_{}_{}".format(i, stage),
        outs = ["mock-cpu_{}_{}_ppa.txt".format(i, stage)],
        arguments = {"OUTFILE": "$(location mock-cpu_{}_{}_ppa.txt)".format(i, stage)},
        script = ":extract_ppa.tcl",
        tags = ["manual"],
    )
    for i in range(N)
    for stage in STAGES
]

# Main DSE optimizer: Find optimal CORE_UTILIZATION and PLACE_DENSITY
py_binary(
    name = "run",
    srcs = [
        "optimize_dse.py",
    ],
    main = "optimize_dse.py",
    tags = ["manual"],
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-pip//kaleido",
        "@bazel-orfs-pip//matplotlib",
        "@bazel-orfs-pip//numpy",
        "@bazel-orfs-pip//optuna",
        "@bazel-orfs-pip//pandas",
        "@bazel-orfs-pip//plotly",
    ],
)
