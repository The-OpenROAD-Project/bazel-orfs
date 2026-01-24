load("//:openroad.bzl", "orfs_flow", "orfs_macro", "orfs_run")

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

orfs_flow(
    name = "sdq_17x64",
    abstract_stage = "cts",
    arguments = FAST_SETTINGS | {
        "CORE_MARGIN": "2",
        "CORE_UTILIZATION": "20",
        "MACRO_PLACE_HALO": "30 30",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
        "PLACE_DENSITY": "0.23",
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
    },
    mock_area = 0.95,
    stage_sources = {
        "synth": [":fakeram/constraints-sram.sdc"],
    },
    verilog_files = [":fakeram/sdq_17x64.sv"],
)

orfs_flow(
    name = "top",
    abstract_stage = "cts",
    arguments = FAST_SETTINGS | {
        "CORE_AREA": "2 2 78 78",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 80 80",
        "MACRO_PLACE_HALO": "2 2",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
    },
    macros = [":sdq_17x64_generate_abstract"],
    stage_sources = {
        "synth": [":fakeram/constraints-sram.sdc"],
    },
    verilog_files = [":fakeram/top.v"],
)

orfs_macro(
    name = "fakeram",
    lef = ":fakeram/sdq_17x64.lef",
    lib = ":fakeram/sdq_17x64.lib",
    module_top = "sdq_17x64",
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "top",
    abstract_stage = "cts",
    arguments = FAST_SETTINGS | {
        "CORE_AREA": "2 2 28 28",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 30 30",
        "MACRO_PLACE_HALO": "2 2",
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
    },
    macros = [":fakeram"],
    sources = {
        "SDC_FILE": [":fakeram/constraints-sram.sdc"],
    },
    variant = "fakeram",
    verilog_files = [":fakeram/top.v"],
)

filegroup(
    name = "lef_file",
    srcs = [
        "sdq_17x64_generate_abstract",
    ],
    output_group = "sdq_17x64.lef",
)

orfs_macro(
    name = "frankenstein",
    lef = ":sdq_17x64_generate_abstract",
    lib = ":fakeram/sdq_17x64.lib",
    module_top = "sdq_17x64",
)

# Use the macro placement from a different flow
orfs_run(
    name = "top_write_macro_placement",
    src = ":top_floorplan_deps",
    outs = [
        ":macro_placement.tcl",
    ],
    arguments = {
        "MESSAGE": "Hello world!",
    },
    # Run only the steps we need, faster
    cmd = "do-2_1_floorplan do-2_2_floorplan_macro run",
    script = ":write_macros.tcl",
)

orfs_run(
    name = "top_write_floorplan",
    src = ":top_floorplan",
    outs = [
        ":floorplan.config",
    ],
    script = ":write_floorplan.tcl",
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "top",
    abstract_stage = "cts",
    arguments = FAST_SETTINGS | {
        "MACRO_PLACEMENT_TCL": "$(location :macro_placement.tcl)",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
    },
    extra_configs = {"floorplan": [":floorplan.config"]},
    macros = [
        ":frankenstein",
    ],
    sources = {
        "MACRO_PLACEMENT_TCL": [":macro_placement.tcl"],
        "SDC_FILE": [":fakeram/constraints-sram.sdc"],
    },
    variant = "mix",
    verilog_files = [":fakeram/top.v"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "sdq_17x64",
    abstract_stage = "place",
    arguments = FAST_SETTINGS | {
        "CORE_MARGIN": "2",
        "CORE_UTILIZATION": "10",
        "MACRO_PLACE_HALO": "30 30",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
        "PLACE_DENSITY": "0.25",
        "SDC_FILE": "$(location :megaboom/constraints-sram.sdc)",
    },
    mock_area = 0.95,
    stage_sources = {
        "synth": [":megaboom/constraints-sram.sdc"],
    },
    variant = "megaboom",
    verilog_files = [":megaboom/sdq_17x64.sv"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "top",
    abstract_stage = "cts",
    arguments = FAST_SETTINGS | {
        "CORE_AREA": "2 2 98 98",
        "CORE_MARGIN": "2",
        "DIE_AREA": "0 0 100 100",
        "MACRO_PLACE_HALO": "2 2",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl",
        "SDC_FILE": "$(location :megaboom/constraints-top.sdc)",
    },
    macros = [":sdq_17x64_megaboom_generate_abstract"],
    stage_sources = {
        "synth": [":megaboom/constraints-top.sdc"],
    },
    variant = "megaboom",
    verilog_files = [":megaboom/top.v"],
)
