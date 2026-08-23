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

def _check_user_hatch(user_dict, label, use_instead):
    """Fails if a project-specific escape hatch names a known ORFS variable."""
    shadowed = sorted([k for k in user_dict if k in ALL_VARIABLE_TO_STAGES])
    if shadowed:
        fail(
            "{label} contains known ORFS variable(s): {shadowed}. ".format(
                label = label,
                shadowed = ", ".join(shadowed),
            ) +
            "Use {use_instead}= for ORFS variables; reserve {label}= for ".format(
                label = label,
                use_instead = use_instead,
            ) +
            "project-specific values.",
        )

def check_stage_variables(arguments, sources, user_arguments, user_sources):
    """Validates a stage target's variable dicts and their escape hatches.

    Shared by every public stage macro (orfs_flow and the per-stage macros in
    flow.bzl) so that a bare orfs_floorplan() gets the same spell-check and
    the same escape-hatch discipline as a full orfs_flow().

    Args:
        arguments: ORFS variable dict; every key must be known.
        sources: ORFS variable dict of source labels; every key must be known.
        user_arguments: project-specific env vars, exempt from the spell-check
            but forbidden from shadowing a known ORFS variable.
        user_sources: as user_arguments, for path hooks.
    """
    check_variables(arguments.keys(), "arguments")
    check_variables(sources.keys(), "sources")
    _check_user_hatch(user_arguments, "user_arguments", "arguments")
    _check_user_hatch(user_sources, "user_sources", "sources")

# ---------------------------------------------------------------------------
# Stage variable filtering — the two time domains
#
# The keep/drop predicate is ONE rule:
#
#     keep variable V for stage-set S  iff
#         S is empty (no filtering)
#         OR V belongs to some stage in S          # union over stages
#         OR V is unmapped (not in variables.yaml) # the escape hatch
#
# It is DECIDED here, at Bazel ANALYSIS time, and nowhere else. It has to be
# APPLIED in two places, because those two places see different things.
#
# 1. ANALYSIS time — get_stage_args() / get_sources() below.
#
#    This one is not really about variables, it is about the ACTION'S INPUT
#    SET: dropping V for a stage also drops the labels in sources[V] from that
#    action's data. That cannot move later:
#      * it prevents circular dependencies (a file produced by a downstream
#        stage must not be wired into an upstream stage's data),
#      * fewer inputs per action lets the action start sooner and cache better,
#      * it lets callers declare one DRY sources={} dict in BUILD.bazel and
#        have each stage take only the subset it needs, and
#      * you CANNOT emit $(locations X) for a label pruned from data —
#        location expansion fails. So the source-derived args must be filtered
#        here, in lockstep with the data entries they name.
#    MORATORIUM(source-filtering-is-analysis-time): never defer source->data
#    filtering to merge_arguments.py.
#
# 2. EXECUTION time — merge_arguments.py, fed the filter .json written by
#    write_stage_filter() in environment.bzl.
#
#    This exists because THE MERGED VARIABLE SET IS NOT KNOWABLE AT ANALYSIS
#    TIME. merge_and_filter_arguments() merges OrfsInfo.arguments, a depset of
#    .json ACTION OUTPUTS:
#      * orfs_arguments (rules.bzl) runs a Tcl script through ORFS — e.g.
#        compute_floorplan_shape.tcl or compute_slack_margin.tcl — and the keys
#        and values it emits only exist after that action has run;
#      * extra_arguments accepts arbitrary generated .json files.
#    A variable can therefore enter the config from a file Starlark has never
#    seen, so the keep/drop has to be applied again by a program running at
#    execution time. That program does NOT re-implement the predicate:
#    Starlark hands it a precomputed DENYLIST (dropped_variables() below) and
#    it applies it verbatim.
#    MORATORIUM(filter-decided-once): merge_arguments.py must stay a denylist
#    APPLIER. Writing the predicate in Python again reintroduces the drift bug
#    this contract removed — a variable kept at analysis time but dropped at
#    execution time (or vice-versa) shows up as a missing-input failure or as
#    silent variable loss on one stage. Locked by test/stages_filter_test.bzl
#    and merge_arguments_test.py.
#
# For inputs only the flow can discover — which macros a synthesized module
# actually instantiates, say — there is a third pattern: DECLARE at analysis
# time, VALIDATE at execution time. kept_macros is declared in BUILD.bazel, so
# macro LEF/lib data can be pruned from action inputs, and rtlil_kept_macros.py
# only checks that declaration against the canonicalized RTLIL, deliberately
# off the critical build graph. Copy that shape rather than growing a new
# execution-time filter.
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
    # The single keep/drop predicate — see the two-time-domains block above.
    return (not filtering) or (arg in allowed) or (arg not in ALL_VARIABLE_TO_STAGES)

def dropped_variables(stages):
    """Returns the denylist that merge_arguments.py applies at execution time.

    Same rule as _keep(), precomputed into the only form merge_arguments.py
    needs: the known variables this stage-set does not own. Unmapped variables
    are never in the list, which is how the escape hatch survives.

    MORATORIUM(filter-decided-once): this is the ONLY place the execution-time
    denylist is computed. See the two-time-domains block above.

    Args:
        stages: list of stage names. Empty means no filtering, so nothing is
            dropped.
    Returns:
      A sorted list of variable names to drop.
    """
    filtering, allowed = _allowed_predicate(stages)
    if not filtering:
        return []
    return sorted([v for v in ALL_VARIABLE_TO_STAGES.keys() if v not in allowed])

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
