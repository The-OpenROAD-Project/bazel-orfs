load("@bazel-orfs//:openroad.bzl", "orfs_flow")
load("@bazel_skylib//rules:common_settings.bzl", "string_flag")

N = 2

[string_flag(
    name = "density{}".format(i),
    build_setting_default = "50",
) for i in range(N)]

[string_flag(
    name = "utilization{}".format(i),
    build_setting_default = "47",
) for i in range(N)]

[orfs_flow(
    name = "lb_32x128_{}".format(i),
    abstract_stage = "place",
    arguments = {
        "CORE_ASPECT_RATIO": "0.5",
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
    settings = {
        "CORE_UTILIZATION": ":utilization{}".format(i),
        "PLACE_DENSITY": ":density{}".format(i),
    },
    sources = {
        "SDC_FILE": ["//optuna:constraints-dse.sdc"],
        "IO_CONSTRAINTS": ["//:io-sram"],
    },
    tags = ["manual"],
    top = "lb_32x128",
    verilog_files = ["//:test/mock/lb_32x128.sv"],
) for i in range(N)]
