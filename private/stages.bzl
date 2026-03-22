"""Stage metadata and argument helpers for OpenROAD-flow-scripts Bazel rules."""

load("@orfs_variable_metadata//:json.bzl", "orfs_variable_metadata")
load("//private:utils.bzl", "flatten", "set", "union")

# A stage argument is used in one or more stages. This is metainformation
# about the ORFS code that there is no known nice way for ORFS to
# provide.
BAZEL_VARIABLE_TO_STAGES = {}

BAZEL_STAGE_TO_VARIABLES = {}

ALL_STAGES = [
    "synth",
    "floorplan",
    "place",
    "cts",
    "grt",
    "route",
    "final",
    "generate_abstract",
    "generate_metadata",
    "test",
    "update_rules",
]

# Substep names within each stage, using ORFS naming directly.
# This is the single source of truth; log_names and json_names in stage
# rules are derived from these lists.
STAGE_SUBSTEPS = {
    "floorplan": [
        "2_1_floorplan",
        "2_2_floorplan_macro",
        "2_3_floorplan_tapcell",
        "2_4_floorplan_pdn",
    ],
    "place": [
        "3_1_place_gp_skip_io",
        "3_2_place_iop",
        "3_3_place_gp",
        "3_4_place_resized",
        "3_5_place_dp",
    ],
    "cts": [
        "4_1_cts",
    ],
    "route": [
        "5_2_route",
        "5_3_fillcell",
    ],
    "final": [
        "6_1_merge",
        "6_report",
    ],
}

# Per-stage metadata used by orfs_flow(squash=True) to combine stages
# into a single Bazel action. Each stage lists its make targets, result
# files, reports, and DRC outputs beyond the substep-derived logs/jsons.
STAGE_METADATA = {
    "floorplan": struct(
        stage_name = "2_floorplan",
        make_targets = ["do-floorplan"],
        result_names = ["2_floorplan.odb", "2_floorplan.sdc"],
        report_names = ["2_floorplan_final.rpt"],
        drc_names = [],
    ),
    "place": struct(
        stage_name = "3_place",
        make_targets = ["do-place"],
        result_names = ["3_place.odb", "3_place.sdc"],
        report_names = [],
        drc_names = [],
    ),
    "cts": struct(
        stage_name = "4_cts",
        make_targets = ["do-cts"],
        result_names = ["4_cts.odb", "4_cts.sdc"],
        report_names = ["4_cts_final.rpt"],
        drc_names = [],
    ),
    "grt": struct(
        stage_name = "5_1_grt",
        make_targets = ["do-5_1_grt"],
        result_names = ["5_1_grt.odb", "5_1_grt.sdc"],
        report_names = ["5_global_route.rpt"],
        drc_names = ["congestion.rpt"],
    ),
    "route": struct(
        stage_name = "5_2_route",
        make_targets = ["do-5_2_route", "do-5_3_fillcell", "do-5_route", "do-5_route.sdc"],
        result_names = ["5_route.odb", "5_route.sdc"],
        report_names = [],
        drc_names = ["5_route_drc.rpt"],
    ),
    "final": struct(
        stage_name = "6_final",
        make_targets = ["do-final"],
        result_names = ["6_final.odb", "6_final.sdc", "6_final.spef", "6_final.v"],
        report_names = ["6_finish.rpt", "VDD.rpt", "VSS.rpt"],
        drc_names = [],
    ),
}

ORFS_VARIABLE_TO_STAGES = {
    k: v["stages"] if "stages" in v and v["stages"] != ["All stages"] else ALL_STAGES
    for k, v in orfs_variable_metadata.items()
}

ORFS_STAGE_TO_VARIABLES = {
    stage: [
        variable
        for variable, has_stages in ORFS_VARIABLE_TO_STAGES.items()
        if stage in has_stages
    ]
    for stage in ALL_STAGES
}

ALL_STAGE_TO_VARIABLES = {
    stage: ORFS_STAGE_TO_VARIABLES.get(stage, [])
    for stage in ALL_STAGES
}

ALL_VARIABLE_TO_STAGES = {
    variable: [
        stage
        for stage in ALL_STAGES
        if variable in ALL_STAGE_TO_VARIABLES[stage]
    ]
    for variable in union(*ALL_STAGE_TO_VARIABLES.values())
}

def get_stage_args(stage, stage_arguments = {}, arguments = {}, sources = {}):
    """Returns the arguments for a specific stage.

    Args:
        stage: The stage name.
        stage_arguments: the dictionary of stages with each stage having a dictionary of arguments
        arguments: a dictionary of arguments automatically assigned to a stage
        sources: a dictionary of variables and source files
    Returns:
      A dictionary of arguments for the stage.
    """
    unsorted_dict = {
        arg: value
        for arg, value in (
            {
                arg: " ".join(["$(locations {})".format(v) for v in value])
                for arg, value in sources.items()
                if arg in ALL_STAGE_TO_VARIABLES[stage] or
                   arg not in ALL_VARIABLE_TO_STAGES
            } |
            {
                arg: value
                for arg, value in arguments.items()
                if arg in ALL_STAGE_TO_VARIABLES[stage] or
                   arg not in ALL_VARIABLE_TO_STAGES
            }
        ).items()
        if arg in ALL_STAGE_TO_VARIABLES[stage] or arg not in ALL_VARIABLE_TO_STAGES
    } | stage_arguments.get(stage, {})
    return dict(sorted(unsorted_dict.items()))

def get_sources(stage, stage_sources, sources):
    """Returns the sources for a specific stage.

    Args:
        stage: The stage name.
        stage_sources: the dictionary of stages with each stage having a list of sources
        sources: a dictionary of variable names with a list of sources to a stage
    Returns:
      A list of sources for the stage.
    """
    return sorted(
        set(
            stage_sources.get(stage, []) +
            flatten(
                [
                    source_list
                    for variable, source_list in sources.items()
                    if variable in ALL_STAGE_TO_VARIABLES[stage] or
                       variable not in ALL_VARIABLE_TO_STAGES
                ],
            ),
        ),
    )
