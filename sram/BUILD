load("//:openroad.bzl", "orfs_flow", "orfs_macro", "orfs_run")

FAST_SETTINGS = {
    "REMOVE_ABC_BUFFERS": "1",
    "SKIP_REPORT_METRICS": "1",
    "SKIP_CTS_REPAIR_TIMING": "1",
    "SKIP_INCREMENTAL_REPAIR": "1",
}

orfs_flow(
    name = "sdq_17x64",
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "CORE_UTILIZATION": "20",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "30 30",
        "PLACE_DENSITY": "0.25",
    },
    mock_area = 0.95,
    stage_outputs = {
        # the "naja" rule below will use the synthesis output
        "synth": {"1_synth.v": "1_synth_unedited.v"},
    },
    stage_sources = {
        "synth": [":fakeram/constraints-sram.sdc"],
        "floorplan": [":naja"],
    },
    verilog_files = [":fakeram/sdq_17x64.sv"],
)

# fish out the file that we want as input to the "naja" rule
# below.
filegroup(
    name = "sdq_17x64_synth_unedited",
    srcs = ["sdq_17x64_synth"],
    output_group = "1_synth_unedited.v",
)

# Read in the renamed synthesis output from above and provide
# the original name to the next stage
genrule(
    name = "naja",
    srcs = [":sdq_17x64_synth_unedited"],
    outs = ["results/asap7/sdq_17x64/base/1_synth.v"],
    cmd = "mkdir -p `dirname $@`; echo \"// imagine naja edits in this file\" > $@ && cat $< >> $@",
)

orfs_flow(
    name = "top",
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "DIE_AREA": "0 0 80 80",
        "CORE_AREA": "2 2 78 78",
        "RTLMP_FLOW": "1",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "2 2",
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
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "DIE_AREA": "0 0 30 30",
        "CORE_AREA": "2 2 28 28",
        "RTLMP_FLOW": "1",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "2 2",
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

# Use the macro placement from a different flow
orfs_run(
    name = "top_write_macro_placement",
    src = ":top_floorplan",
    outs = [
        ":macro_placement.tcl",
    ],
    arguments = {
        "MESSAGE": "Hello world!",
    },
    script = ":write_macros.tcl",
)

orfs_run(
    name = "top_write_floorplan",
    src = ":top_floorplan_deps",
    outs = [
        ":floorplan.config",
    ],
    script = ":write_floorplan.tcl",
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "top",
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
        "MACRO_PLACEMENT_TCL": "$(location :macro_placement.tcl)",
        "ADDITIONAL_LEFS": "$(location :lef_file)",
        "ADDITIONAL_LIBS": "$(location :fakeram/sdq_17x64.lib)",
        "RTLMP_FLOW": "1",
    },
    extra_configs = {"floorplan": [":floorplan.config"]},
    sources = {
        "SDC_FILE": [":fakeram/constraints-sram.sdc"],
        "ADDITIONAL_LEFS": [":lef_file"],
        "ADDITIONAL_LIBS": [":fakeram/sdq_17x64.lib"],
        "MACRO_PLACEMENT_TCL": [":macro_placement.tcl"],
    },
    variant = "mix",
    verilog_files = [":fakeram/top.v"],
)

# buildifier: disable=duplicated-name
orfs_flow(
    name = "sdq_17x64",
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :megaboom/constraints-sram.sdc)",
        "CORE_UTILIZATION": "20",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "30 30",
        "PLACE_DENSITY": "0.25",
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
    abstract_stage = "grt",
    arguments = FAST_SETTINGS | {
        "SDC_FILE": "$(location :megaboom/constraints-top.sdc)",
        "DIE_AREA": "0 0 100 100",
        "CORE_AREA": "2 2 98 98",
        "RTLMP_FLOW": "1",
        "CORE_MARGIN": "2",
        "MACRO_PLACE_HALO": "2 2",
    },
    macros = [":sdq_17x64_megaboom_generate_abstract"],
    stage_sources = {
        "synth": [":megaboom/constraints-top.sdc"],
    },
    variant = "megaboom",
    verilog_files = [":megaboom/top.v"],
)
