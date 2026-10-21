"""Unit tests for the repeatable-synthesis default in private/flow.bzl.

bazel-orfs synthesises with SYNTH_REPEATABLE_BUILD=1 unless a design sets
it: ORFS keeps the debug information a person reading a netlist wants,
bazel-orfs wants the cache hit that information costs.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:flow.bzl", "repeatable_arguments")

def _default_is_repeatable_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        {"SYNTH_REPEATABLE_BUILD": "1"},
        repeatable_arguments({}),
        "a design that does not set it synthesises repeatably",
    )
    asserts.equals(
        env,
        {"CORE_UTILIZATION": "10", "SYNTH_REPEATABLE_BUILD": "1"},
        repeatable_arguments({"CORE_UTILIZATION": "10"}),
        "the other arguments are untouched",
    )
    return unittest.end(env)

def _design_setting_kept_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        {"SYNTH_REPEATABLE_BUILD": "0"},
        repeatable_arguments({"SYNTH_REPEATABLE_BUILD": "0"}),
        "a design that asks for ORFS's netlist gets it",
    )
    return unittest.end(env)

default_is_repeatable_test = unittest.make(_default_is_repeatable_test)
design_setting_kept_test = unittest.make(_design_setting_kept_test)

def repeatable_default_test_suite(name):
    unittest.suite(
        name,
        default_is_repeatable_test,
        design_setting_kept_test,
    )
