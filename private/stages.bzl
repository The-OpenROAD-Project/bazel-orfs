"""Stage metadata and argument helpers for OpenROAD-flow-scripts Bazel rules."""

load("@orfs_variable_metadata//:json.bzl", "orfs_variable_metadata")
load("//private:utils.bzl", "flatten", "set", "union")

# A stage argument is used in one or more stages. This is metainformation
# about the ORFS code that there is no known nice way for ORFS to
# provide.
#
# Variables auto-injected by bazel-orfs (not present in ORFS variables.yaml)
# are registered here so that check_variables() does not flag them as
# unknown when downstream callers see them in arguments.
ALL_STAGES_LIST = [
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

BAZEL_VARIABLE_TO_STAGES = {
    # Set in orfs_design.bzl when SYNTH_HIERARCHICAL=1.
    "SYNTH_NUM_PARTITIONS": ["synth"],
    "PLATFORM": ALL_STAGES_LIST,
    "PLATFORM_DIR": ALL_STAGES_LIST,
    "DESIGN_NAME": ALL_STAGES_LIST,
}

BAZEL_STAGE_TO_VARIABLES = {
    stage: [v for v, stages in BAZEL_VARIABLE_TO_STAGES.items() if stage in stages]
    for stage in ALL_STAGES_LIST
}

ALL_STAGES = ALL_STAGES_LIST

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
    "grt": [
        "5_1_grt",
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
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["floorplan"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["floorplan"]],
        result_names = ["2_floorplan.odb", "2_floorplan.sdc"],
        report_names = ["2_floorplan_final.rpt"],
        drc_names = [],
    ),
    "place": struct(
        stage_name = "3_place",
        make_targets = ["do-place"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["place"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["place"]],
        result_names = ["3_place.odb", "3_place.sdc"],
        report_names = [],
        drc_names = [],
    ),
    "cts": struct(
        stage_name = "4_cts",
        make_targets = ["do-cts"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["cts"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["cts"]],
        result_names = ["4_cts.odb", "4_cts.sdc"],
        report_names = ["4_cts_final.rpt"],
        drc_names = [],
    ),
    "grt": struct(
        stage_name = "5_1_grt",
        make_targets = ["do-5_1_grt"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["grt"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["grt"]],
        result_names = ["5_1_grt.odb", "5_1_grt.sdc"],
        report_names = ["5_global_route.rpt"],
        drc_names = ["congestion.rpt"],
    ),
    "route": struct(
        stage_name = "5_2_route",
        make_targets = ["do-5_2_route", "do-5_3_fillcell", "do-5_route", "do-5_route.sdc"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["route"]],
        json_names = [s + ".json" for s in STAGE_SUBSTEPS["route"]],
        result_names = ["5_route.odb", "5_route.sdc"],
        report_names = [],
        drc_names = ["5_route_drc.rpt"],
    ),
    "final": struct(
        stage_name = "6_final",
        make_targets = ["do-final"],
        log_names = [s + ".log" for s in STAGE_SUBSTEPS["final"]],
        json_names = [
            "6_report.json",
            "6_1_fill.json",
        ],
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
    stage: ORFS_STAGE_TO_VARIABLES.get(stage, []) +
           BAZEL_STAGE_TO_VARIABLES.get(stage, [])
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

def check_variables(variables, label):
    """Checks that all variable names are known in ORFS variables.yaml.

    Args:
        variables: iterable of variable names to check.
        label: description of where the variables came from (for error messages).
    """
    unknown = sorted([v for v in variables if v not in ALL_VARIABLE_TO_STAGES])
    if unknown:
        fail(
            "Unknown ORFS variable(s) in {label}: {unknown}. ".format(
                label = label,
                unknown = ", ".join(unknown),
            ) +
            "Check spelling against ORFS flow/scripts/variables.yaml. " +
            "If the variable is correct but missing from variables.yaml, " +
            "add it to your project's ORFS patch or file a PR against ORFS.",
        )

# ---------------------------------------------------------------------------
# Stage variable filtering
#
# get_stage_args() and get_sources() implement the SAME keep/drop predicate:
#
#     keep variable V for stage-set S  iff
#         S is empty (no filtering)
#         OR V belongs to some stage in S         # union over stages
#         OR V is unmapped (not in variables.yaml) # the escape hatch
#
# This module is the canonical documentation hub for the filter invariants;
# other sites point back here by MORATORIUM tag (grep `MORATORIUM(` to
# enumerate all fences).
#
# MORATORIUM(filter-parity): This predicate is mirrored at EXECUTION time by
# merge_arguments.py (`drop iff k in known and k not in allowed`) and by the
# inline filter_json in rules.bzl (synth partitions). All three MUST agree —
# if they drift, a variable can be kept at analysis time but dropped at
# execution time (or vice-versa), causing missing-input failures or silent
# variable loss on specific stages. Change them together; the filter-parity
# behavior is locked by test/stages_filter_test.bzl and merge_arguments_test.py.
#
# MORATORIUM(source-filtering-is-analysis-time): get_sources() filters at
# Bazel ANALYSIS time on purpose, and a source's $(locations) argument is
# filtered here in lockstep with its data entry. This is not optional:
#   * it prevents circular dependencies (a source consumed by a downstream
#     stage must not be wired into an upstream stage's data),
#   * fewer inputs per action lets the action start sooner, and
#   * it lets callers declare one DRY sources={} dict in BUILD.bazel and have
#     each stage take only the subset it needs.
# Never defer source->data filtering to merge_arguments.py. You also cannot
# emit $(locations X) for a label pruned from data (location-expansion error),
# which is why the source-derived args live here and not with plain args.
#
# The `stages` parameter is always a LIST (empty = no filtering). flow.bzl
# wraps its single stage as [stage]; orfs_run passes its stages string_list.
# ---------------------------------------------------------------------------

def _allowed_predicate(stages):
    """Returns (filtering, allowed) for the keep/drop predicate.

    Args:
        stages: list of stage names. Empty means no filtering.
    Returns:
      A tuple (filtering, allowed) where `filtering` is True when a non-empty
      stage list was given, and `allowed` is an O(1)-membership dict of the
      variables owned by any of those stages.
    """
    if not stages:
        return False, {}
    allowed = {}
    for stage in stages:
        for variable in ALL_STAGE_TO_VARIABLES[stage]:
            allowed[variable] = True
    return True, allowed

def _keep(arg, filtering, allowed):
    # See the MORATORIUM(filter-parity) note above — this is the single
    # analysis-time keep/drop predicate.
    return (not filtering) or (arg in allowed) or (arg not in ALL_VARIABLE_TO_STAGES)

def get_stage_args(stages, stage_arguments = {}, arguments = {}, sources = {}):
    """Returns the arguments for a set of stages.

    Args:
        stages: list of stage names to keep arguments for (empty = keep all).
        stage_arguments: dict keyed by stage, each holding a dict of arguments.
            These are authored per-stage and BYPASS the variable filter on
            purpose — do not fold them into the filtered dict below.
            MORATORIUM(stage-arguments-bypass): locked by
            test/stages_filter_test.bzl.
        arguments: a dictionary of arguments automatically assigned to a stage
        sources: a dictionary of variables and source files
    Returns:
      A dictionary of arguments for the stage(s).
    """
    filtering, allowed = _allowed_predicate(stages)

    # stage_arguments are pre-scoped by stage key, so they are added AFTER the
    # filter (MORATORIUM(stage-arguments-bypass)). Merge every requested stage.
    stage_specific = {}
    for stage in stages:
        stage_specific.update(stage_arguments.get(stage, {}))

    unsorted_dict = {
        arg: " ".join(["$(locations {})".format(v) for v in value])
        for arg, value in sources.items()
        if _keep(arg, filtering, allowed)
    }
    unsorted_dict.update({
        arg: value
        for arg, value in arguments.items()
        if _keep(arg, filtering, allowed)
    })
    unsorted_dict.update(stage_specific)

    # sorted() output is load-bearing for deterministic action command lines
    # — do not remove.
    return dict(sorted(unsorted_dict.items()))

def get_sources(stages, sources):
    """Returns the sources for a set of stages.

    Args:
        stages: list of stage names to keep sources for (empty = keep all).
        sources: a dictionary of variable names with a list of sources to a stage
    Returns:
      A sorted, de-duplicated list of sources for the stage(s).
    """
    filtering, allowed = _allowed_predicate(stages)

    # sorted(set(...)) is load-bearing: set() de-duplicates sources shared
    # across variables, sorted() gives deterministic inputs.
    return sorted(
        set(
            flatten(
                [
                    source_list
                    for variable, source_list in sources.items()
                    if _keep(variable, filtering, allowed)
                ],
            ),
        ),
    )
