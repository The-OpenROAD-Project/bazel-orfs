load("//:openroad.bzl", "orfs_flow", "orfs_run")

FAST_SETTINGS = {
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_REPORT_METRICS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_INCREMENTAL_REPAIR": "1",
}

orfs_flow(
    name = "sdq_17x64",
    abstract_stage = "grt",
    mock_area = 0.95,
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "CORE_UTILIZATION": "20",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "30 30",
        "PLACE_DENSITY": "0.25",
    },
    stage_sources = {
        "synth": [":fakeram/constraints-sram.sdc"],
    },
    verilog_files = [":fakeram/sdq_17x64.sv"],
)

orfs_flow(
    name = "top",
    abstract_stage = "grt",
    macros = [":sdq_17x64_generate_abstract"],
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "DIE_AREA": "0 0 80 80",
        "CORE_AREA": "2 2 78 78",
        "RTLMP_FLOW": "True",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "2 2",
    },
    stage_sources = {
        "synth": [":fakeram/constraints-sram.sdc"],
    },
    verilog_files = [":fakeram/top.v"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "top",
    variant = "fakeram",
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "DIE_AREA": "0 0 30 30",
        "CORE_AREA": "2 2 28 28",
        "RTLMP_FLOW": "True",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "2 2",
        "ADDITIONAL_LEFS": "$(location :fakeram/sdq_17x64.lef)",
        "ADDITIONAL_LIBS": "$(location :fakeram/sdq_17x64.lib)",
    },
    sources = {
        "ADDITIONAL_LEFS": [":fakeram/sdq_17x64.lef"],
        "ADDITIONAL_LIBS": [":fakeram/sdq_17x64.lib"],
        "SDC_FILE": [":fakeram/constraints-sram.sdc"],
    },
    verilog_files = [":fakeram/top.v"],
)

filegroup(
    name = "lef_file",
    srcs = [
        "sdq_17x64_generate_abstract",
    ],
    output_group = "sdq_17x64.lef",
)

# Use the macro placement from a different flow
orfs_run(
    name = "top_write_macro_placement",
    src = ":top_floorplan",
    arguments = {
        "MESSAGE": "Hello world!",
    },
    outs = [
        ":macro_placement.tcl",
    ],
    script = ":write_macros.tcl",
)

orfs_run(
    name = "top_write_floorplan",
    src = ":top_floorplan_deps",
    outs = [
        ":floorplan.def",
    ],
    script = ":write_floorplan.tcl",
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "top",
    variant = "mix",
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "FLOORPLAN_DEF": "$(location :floorplan.def)",
        "MACRO_PLACEMENT_TCL": "$(location :macro_placement.tcl)",
        "ADDITIONAL_LEFS": "$(location :lef_file)",
        "ADDITIONAL_LIBS": "$(location :fakeram/sdq_17x64.lib)",
    },
    sources = {
        "SDC_FILE": [":fakeram/constraints-sram.sdc"],
        "FLOORPLAN_DEF": ":floorplan.def",
        "ADDITIONAL_LEFS": [":lef_file"],
        "ADDITIONAL_LIBS": [":fakeram/sdq_17x64.lib"],
        "MACRO_PLACEMENT_TCL": [":macro_placement.tcl"],
    },
    verilog_files = [":fakeram/top.v"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "sdq_17x64",
    variant = "megaboom",
    abstract_stage = "grt",
    mock_area = 0.95,
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :megaboom/constraints-sram.sdc)",
        "CORE_UTILIZATION": "20",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "30 30",
        "PLACE_DENSITY": "0.25",
    },
    stage_sources = {
        "synth": [":megaboom/constraints-sram.sdc"],
    },
    verilog_files = [":megaboom/sdq_17x64.sv"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "top",
    abstract_stage = "grt",
    variant = "megaboom",
    macros = [":sdq_17x64_megaboom_generate_abstract"],
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :megaboom/constraints-top.sdc)",
        "DIE_AREA": "0 0 100 100",
        "CORE_AREA": "2 2 98 98",
        "RTLMP_FLOW": "True",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "2 2",
    },
    stage_sources = {
        "synth": [":megaboom/constraints-top.sdc"],
    },
    verilog_files = [":megaboom/top.v"],
)
