"""Unit tests for the OpenROAD hierarchical-mode default in private/flow.bzl.

bazel-orfs runs OpenROAD with OPENROAD_HIERARCHICAL=1 unless a design
sets it: ORFS's own description says hierarchical mode will become the
default and the option will be retired, so the flat mode is the
exception a design states.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:flow.bzl", "hierarchical_arguments")

def _default_is_hierarchical_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        {"OPENROAD_HIERARCHICAL": "1"},
        hierarchical_arguments({}),
        "a design that does not set the mode runs hierarchical",
    )
    asserts.equals(
        env,
        {"CORE_UTILIZATION": "10", "OPENROAD_HIERARCHICAL": "1"},
        hierarchical_arguments({"CORE_UTILIZATION": "10"}),
        "the other arguments are untouched",
    )
    return unittest.end(env)

def _design_setting_kept_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        {"OPENROAD_HIERARCHICAL": "0"},
        hierarchical_arguments({"OPENROAD_HIERARCHICAL": "0"}),
        "a design that asks for flat stays flat",
    )
    return unittest.end(env)

default_is_hierarchical_test = unittest.make(_default_is_hierarchical_test)
design_setting_kept_test = unittest.make(_design_setting_kept_test)

def hierarchical_default_test_suite(name):
    unittest.suite(
        name,
        default_is_hierarchical_test,
        design_setting_kept_test,
    )
