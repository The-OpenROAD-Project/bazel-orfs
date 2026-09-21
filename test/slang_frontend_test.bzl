"""Unit tests for the synthesis-frontend policy in private/flow.bzl.

bazel-orfs synthesises with slang. The policy lives in one function so
that both public entry points that run synthesis -- orfs_flow() and a
standalone orfs_synth() -- give a design the same frontend; before that
the same RTL could take either one depending on which macro declared it.

What is covered here is the value the policy returns. The refusal is a
macro-level fail() at package load, which no bazel test can catch:
loading the package is the assertion, so a target that must be refused
cannot be declared anywhere. The other half -- that
yosys_frontend_reason is consumed by the macro and never reaches the
rule as an unknown attribute -- is pinned by declaring such a target in
test/BUILD, the same way the user_stages companions are.
"""

load("@bazel_skylib//lib:unittest.bzl", "asserts", "unittest")
load("//private:flow.bzl", "slang_arguments")

def _default_is_slang_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(
        env,
        {"SYNTH_HDL_FRONTEND": "slang"},
        slang_arguments("orfs_flow", "t", {}, None),
        "a design that names no frontend gets slang",
    )
    asserts.equals(
        env,
        {"CORE_UTILIZATION": "10", "SYNTH_HDL_FRONTEND": "slang"},
        slang_arguments("orfs_flow", "t", {"CORE_UTILIZATION": "10"}, None),
        "the other arguments are untouched",
    )
    return unittest.end(env)

def _explicit_slang_test(ctx):
    env = unittest.begin(ctx)

    # Saying slang out loud needs no reason, and changes nothing.
    asserts.equals(
        env,
        {"SYNTH_HDL_FRONTEND": "slang"},
        slang_arguments("orfs_flow", "t", {"SYNTH_HDL_FRONTEND": "slang"}, None),
    )
    return unittest.end(env)

def _reasoned_exception_test(ctx):
    env = unittest.begin(ctx)

    # With a reason, the frontend the design asked for survives: the
    # policy is "say why", not "slang or nothing".
    asserts.equals(
        env,
        {"SYNTH_HDL_FRONTEND": "verific"},
        slang_arguments(
            "orfs_flow",
            "t",
            {"SYNTH_HDL_FRONTEND": "verific"},
            "the RTL uses a construct slang rejects",
        ),
    )
    return unittest.end(env)

def _synth_use_syn_is_exempt_test(ctx):
    env = unittest.begin(ctx)

    # SYNTH_USE_SYN bypasses yosys altogether, so the frontend is not
    # its question: nothing is added, and an unreasoned non-slang
    # setting is not refused either.
    asserts.equals(
        env,
        {"SYNTH_USE_SYN": "1"},
        slang_arguments("orfs_flow", "t", {"SYNTH_USE_SYN": "1"}, None),
    )
    asserts.equals(
        env,
        {"SYNTH_USE_SYN": "1", "SYNTH_HDL_FRONTEND": "verific"},
        slang_arguments(
            "orfs_flow",
            "t",
            {"SYNTH_USE_SYN": "1", "SYNTH_HDL_FRONTEND": "verific"},
            None,
        ),
    )
    return unittest.end(env)

default_is_slang_test = unittest.make(_default_is_slang_test)
explicit_slang_test = unittest.make(_explicit_slang_test)
reasoned_exception_test = unittest.make(_reasoned_exception_test)
synth_use_syn_is_exempt_test = unittest.make(_synth_use_syn_is_exempt_test)

def slang_frontend_test_suite(name):
    unittest.suite(
        name,
        default_is_slang_test,
        explicit_slang_test,
        reasoned_exception_test,
        synth_use_syn_is_exempt_test,
    )
