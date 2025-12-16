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

[orfs_flow(
    name = "sdq_17x64",
    abstract_stage = "cts" if variant == "base" else "place",
    arguments = FAST_SETTINGS | {
        "CORE_MARGIN": "2",
        "CORE_UTILIZATION": "20",
        "MACRO_PLACE_HALO": "30 30",
        "PDN_TCL": "$(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl",
        "PLACE_DENSITY": "0.23",
        "SDC_FILE": "$(location :fakeram/constraints-sram.sdc)",
    },
    mock_area = 0.95,
    previous_stage = {
        "mock-naja": {
            "floorplan": "sdq_17x64_synth",
        },
    }.get(variant, {}),
    renamed_inputs = {
        "mock-naja": {
            "floorplan": {"1_synth.v": ":mock-naja"},
        },
        "naja": {
            "floorplan": {"1_synth.v": ":naja"},
        },
        "naja-error": {
            "floorplan": {"1_synth.v": ":naja-error"},
        },
    }.get(variant, {}),
    stage_sources = {
        "synth": [":fakeram/constraints-sram.sdc"],
    },
    tags = {
        "naja": ["manual"],
        "naja-error": ["manual"],
    }.get(variant, []),
    variant = variant,
    verilog_files = [":fakeram/sdq_17x64.sv"],
) for variant in [
    "base",
    #    "mock-naja",
    #    "naja",
    #    "naja-error",
]]

# fish out the file that we want as input to the "naja" rule
# below.
filegroup(
    name = "sdq_17x64_synth_unedited",
    srcs = ["sdq_17x64_naja_synth"],
    output_group = "1_synth.v",
)

orfs_run(
    name = "sdq_17x64_synth_mergedlib",
    src = ":sdq_17x64_naja_synth",
    outs = [":objects/asap7/sdq_17x64/naja/lib/merged.lib"],
    extra_args = " ".join([
        "$(location :objects/asap7/sdq_17x64/naja/lib/merged.lib)",
    ]),
    script = "@docker_orfs//:OpenROAD-flow-scripts/flow/scripts/noop.tcl",
    tags = ["manual"],
)

filegroup(
    name = "top_lib",
    srcs = ["top_generate_abstract"],
    output_group = "top_typ.lib",
)

# Read in the renamed synthesis output from above and provide
# the original name to the next stage
genrule(
    name = "mock-naja",
    srcs = [
        ":sdq_17x64_synth_unedited",
        ":sdq_17x64_synth_mergedlib",
        ":top_lib",
    ],
    outs = ["mock-naja.v"],
    cmd = """
    set -e
    mkdir -p `dirname $@`
    # reference files we should be able to access here
    ls $(location :sdq_17x64_synth_mergedlib) $(location :top_lib) > /dev/null
    echo \"// imagine naja edits in this file\" > $@
    cat $(location :sdq_17x64_synth_unedited) >> $@
""",
    tags = ["manual"],
)

# FIXME some better way to deploy naja in Bazel environment is needed
genrule(
    name = "naja",
    srcs = [
        ":sdq_17x64_synth_unedited",
        ":sdq_17x64_synth_mergedlib",
        "naja_edit/install/bin/naja_edit",
        "naja_edit/install/lib/python",
        "naja_edit/install/share/naja/primitives/asap7_new.py",
    ],
    outs = ["naja.v"],
    cmd = "mkdir -p `dirname $@`; export PYTHONPATH=$(location naja_edit/install/lib/python) && $(location naja_edit/install/bin/naja_edit) -a all -p $(location :sdq_17x64_synth_mergedlib) -f verilog -t verilog -i $(location :sdq_17x64_synth_unedited) -o $@",
    tags = ["manual"],
)

genrule(
    name = "naja-error",
    srcs = [":sdq_17x64_synth_unedited"],
    outs = ["naja-error.v"],
    cmd = "mkdir -p `dirname $@`; echo \"imagine naja producing invalid verilog\" > $@ && cat $< >> $@",
    tags = ["manual"],
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
