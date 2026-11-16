"""analysistest: target_under_test fails analysis with message.

Every test that expects an analysis failure uses this rule: CI analyses
every manual target except the targets_under_test of this kind.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _refused_impl(ctx):
    env = analysistest.begin(ctx)
    asserts.expect_failure(env, ctx.attr.message)
    return analysistest.end(env)

analysis_failure_test = analysistest.make(
    _refused_impl,
    attrs = {
        "message": attr.string(mandatory = True),
    },
    expect_failure = True,
)
