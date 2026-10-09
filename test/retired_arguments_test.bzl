"""analysistest: a retired variable is refused, naming what replaced it.

STRUCTURED_MEMORIES and STRUCTURED_PLACEMENT were bazel-orfs's own ORFS
patches, retired for AUTO_MEMORIES_REGFILES and AUTO_MEMORIES_MACRO_PLACE.
ORFS ignores a variable it does not know, so a flow that still set one
would build, without the register files it asked for. The refusal is a
fail() in the stage rules, so it holds for orfs_flow and a standalone
stage alike.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _refused_impl(ctx):
    env = analysistest.begin(ctx)
    asserts.expect_failure(env, ctx.attr.message)
    return analysistest.end(env)

retired_argument_test = analysistest.make(
    _refused_impl,
    attrs = {
        "message": attr.string(mandatory = True),
    },
    expect_failure = True,
)
