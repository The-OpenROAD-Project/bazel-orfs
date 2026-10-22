"""analysistest: a stage refuses a src built with other macros than its flow's.

A stage after synthesis takes its macros' LEF and liberty files from src,
not from its flow's macros. A flow that shares another flow's synthesis
through previous_stage while naming other macros would place the shared
synthesis's macros, silently. The first stage after previous_stage checks
them, at analysis.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _refused_impl(ctx):
    env = analysistest.begin(ctx)
    asserts.expect_failure(env, ctx.attr.message)
    return analysistest.end(env)

macros_check_test = analysistest.make(
    _refused_impl,
    attrs = {
        "message": attr.string(mandatory = True),
    },
    expect_failure = True,
)
