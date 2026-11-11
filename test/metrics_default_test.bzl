"""Unit tests for the skipped-metrics default in private/flow.bzl.

bazel-orfs builds every stage with SKIP_REPORT_METRICS=1 unless a design
sets it: the timing and power metrics come from <stage>_report, built on
the stage's saved results when asked for.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:flow.bzl", "metrics_arguments")

def _default_skips_metrics_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        {"SKIP_REPORT_METRICS": "1"},
        metrics_arguments({}),
        "a design that does not set it skips report_metrics in-stage",
    )
    asserts.equals(
        env,
        {"CORE_UTILIZATION": "10", "SKIP_REPORT_METRICS": "1"},
        metrics_arguments({"CORE_UTILIZATION": "10"}),
        "the other arguments are untouched",
    )
    return unittest.end(env)

def _design_metrics_kept_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        {"SKIP_REPORT_METRICS": "0"},
        metrics_arguments({"SKIP_REPORT_METRICS": "0"}),
        "a design that wants metrics in its stage .json gets them",
    )
    return unittest.end(env)

default_skips_metrics_test = unittest.make(_default_skips_metrics_test)
design_metrics_kept_test = unittest.make(_design_metrics_kept_test)

def metrics_default_test_suite(name):
    unittest.suite(
        name,
        default_skips_metrics_test,
        design_metrics_kept_test,
    )
