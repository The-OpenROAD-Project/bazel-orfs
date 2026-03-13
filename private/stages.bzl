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
