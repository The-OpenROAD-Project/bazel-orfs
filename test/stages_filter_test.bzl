"""Unit tests for the stage variable filtering helpers in stages.bzl.

Covers the keep/drop predicate shared by get_stage_args() and get_sources()
and the invariants documented by the MORATORIUM blocks in private/stages.bzl:

  * empty stages list means "keep everything", not "keep nothing";
  * unmapped variables (absent from variables.yaml) always survive (the
    escape hatch);
  * MORATORIUM(stage-arguments-bypass): stage_arguments bypass the filter;
  * MORATORIUM(filter-decided-once): dropped_variables(), the denylist handed
    to merge_arguments.py at execution time, is the exact complement of the
    analysis-time keep predicate;
  * output is sorted/deterministic;
  * list union — a variable in ANY requested stage is kept.

Inputs are derived from the live ORFS metadata dicts so the test does not
hard-code any particular variable-to-stage mapping.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load(
    "//private:stages.bzl",
    "ALL_STAGE_TO_VARIABLES",
    "ALL_VARIABLE_TO_STAGES",
    "dropped_variables",
    "get_sources",
    "get_stage_args",
)

# A name guaranteed not to be a known ORFS variable (the unmapped escape hatch).
_UNMAPPED = "ZZ_UNMAPPED_TEST_VAR"

# Pick two distinct stages A and B such that A owns a variable B does not, and
# B owns a variable A does not. Derived from live metadata for robustness.
def _pick_stages():
    stages = sorted(ALL_STAGE_TO_VARIABLES.keys())
    for a in stages:
        a_vars = ALL_STAGE_TO_VARIABLES[a]
        for b in stages:
            if b == a:
                continue
            b_vars = ALL_STAGE_TO_VARIABLES[b]
            only_a = [v for v in a_vars if v not in b_vars]
            only_b = [v for v in b_vars if v not in a_vars]
            if only_a and only_b:
                return a, only_a[0], b, only_b[0]
    return None, None, None, None

_STAGE_A, _VAR_A, _STAGE_B, _VAR_B = _pick_stages()

def _empty_stages_keeps_everything_test(ctx):
    env = unittest.begin(ctx)

    # A mapped variable that WOULD be dropped if filtered by an unrelated
    # stage, plus an unmapped one — both must survive when stages is empty.
    sources = {_VAR_A: ["//a:la"], _UNMAPPED: ["//u:lu"]}
    asserts.equals(env, ["//a:la", "//u:lu"], get_sources([], sources))
    asserts.equals(
        env,
        {_VAR_A: "$(locations //a:la)", _UNMAPPED: "$(locations //u:lu)"},
        get_stage_args([], sources = sources),
    )
    return unittest.end(env)

def _filter_drops_out_of_stage_keeps_unmapped_test(ctx):
    env = unittest.begin(ctx)

    # _VAR_B belongs to stage B, not A -> dropped when filtering by [A].
    # _UNMAPPED is unknown -> kept (escape hatch). _VAR_A -> kept.
    sources = {_VAR_A: ["//a:la"], _VAR_B: ["//b:lb"], _UNMAPPED: ["//u:lu"]}
    asserts.equals(env, ["//a:la", "//u:lu"], get_sources([_STAGE_A], sources))
    asserts.equals(
        env,
        {_VAR_A: "$(locations //a:la)", _UNMAPPED: "$(locations //u:lu)"},
        get_stage_args([_STAGE_A], sources = sources),
    )
    return unittest.end(env)

def _union_over_stages_test(ctx):
    env = unittest.begin(ctx)

    # Filtering by [A, B] keeps variables owned by either stage.
    sources = {_VAR_A: ["//a:la"], _VAR_B: ["//b:lb"]}
    asserts.equals(
        env,
        ["//a:la", "//b:lb"],
        get_sources([_STAGE_A, _STAGE_B], sources),
    )
    return unittest.end(env)

def _stage_arguments_bypass_filter_test(ctx):
    env = unittest.begin(ctx)

    # _VAR_B is out-of-stage for [A], but a stage_argument keyed to A that
    # sets it must still appear — MORATORIUM(stage-arguments-bypass).
    result = get_stage_args(
        [_STAGE_A],
        stage_arguments = {_STAGE_A: {_VAR_B: "forced"}},
    )
    asserts.equals(env, "forced", result.get(_VAR_B))
    return unittest.end(env)

def _denylist_is_the_complement_of_keep_test(ctx):
    env = unittest.begin(ctx)

    # MORATORIUM(filter-decided-once): the execution-time denylist must agree
    # with the analysis-time keep predicate for every known variable, so that
    # merge_arguments.py never has to re-derive it.
    dropped = dropped_variables([_STAGE_A])
    kept = ALL_STAGE_TO_VARIABLES[_STAGE_A]

    # Nothing this stage owns is dropped, and every known variable it does not
    # own is.
    asserts.equals(env, [], [v for v in dropped if v in kept])
    asserts.equals(
        env,
        [],
        [v for v in ALL_VARIABLE_TO_STAGES.keys() if v not in kept and v not in dropped],
    )

    # Unmapped variables are never on the denylist — the escape hatch.
    asserts.false(env, _UNMAPPED in dropped)

    # Sorted for deterministic action inputs.
    asserts.equals(env, sorted(dropped), dropped)

    # No stages means no filtering, so nothing is dropped.
    asserts.equals(env, [], dropped_variables([]))
    return unittest.end(env)

def _denylist_union_over_stages_test(ctx):
    env = unittest.begin(ctx)

    # A variable owned by either stage survives a two-stage filter.
    dropped = dropped_variables([_STAGE_A, _STAGE_B])
    asserts.false(env, _VAR_A in dropped)
    asserts.false(env, _VAR_B in dropped)

    # ... but it is dropped when only the other stage is requested.
    asserts.true(env, _VAR_B in dropped_variables([_STAGE_A]))
    return unittest.end(env)

def _sorted_output_test(ctx):
    env = unittest.begin(ctx)

    # Keys come back sorted regardless of insertion order (determinism).
    result = get_stage_args([], arguments = {"ZED": "1", "ALPHA": "2", "MID": "3"})
    asserts.equals(env, ["ALPHA", "MID", "ZED"], result.keys())
    return unittest.end(env)

empty_stages_keeps_everything_test = unittest.make(_empty_stages_keeps_everything_test)
filter_drops_out_of_stage_keeps_unmapped_test = unittest.make(_filter_drops_out_of_stage_keeps_unmapped_test)
union_over_stages_test = unittest.make(_union_over_stages_test)
stage_arguments_bypass_filter_test = unittest.make(_stage_arguments_bypass_filter_test)
denylist_is_the_complement_of_keep_test = unittest.make(_denylist_is_the_complement_of_keep_test)
denylist_union_over_stages_test = unittest.make(_denylist_union_over_stages_test)
sorted_output_test = unittest.make(_sorted_output_test)

def stages_filter_test_suite(name):
    unittest.suite(
        name,
        empty_stages_keeps_everything_test,
        filter_drops_out_of_stage_keeps_unmapped_test,
        union_over_stages_test,
        stage_arguments_bypass_filter_test,
        denylist_is_the_complement_of_keep_test,
        denylist_union_over_stages_test,
        sorted_output_test,
    )
