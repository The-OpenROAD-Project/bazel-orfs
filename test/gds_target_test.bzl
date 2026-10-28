"""analysistest: orfs_flow()'s <name>_gds runs the klayout it should.

Every orfs_flow() that runs to final has a <name>_gds. Its klayout is,
in order, the flow's own klayout = ..., --@bazel-orfs//:klayout_tool,
then orfs.default(klayout = ...). Checks the KLAYOUT_CMD the target's
actions are given.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _gds_klayout_test_impl(ctx):
    env = analysistest.begin(ctx)
    cmds = [
        a.env["KLAYOUT_CMD"]
        for a in analysistest.target_actions(env)
        if a.env and "KLAYOUT_CMD" in a.env
    ]
    label = analysistest.target_under_test(env).label
    asserts.true(env, len(cmds) > 0, "%s: no action sets KLAYOUT_CMD" % label)
    for cmd in cmds:
        asserts.true(
            env,
            ctx.attr.klayout in cmd,
            "%s: KLAYOUT_CMD is %s, expected it to name %s" % (label, cmd, ctx.attr.klayout),
        )
    return analysistest.end(env)

gds_klayout_test = analysistest.make(
    _gds_klayout_test_impl,
    attrs = {
        "klayout": attr.string(mandatory = True),
    },
)

gds_klayout_flag_test = analysistest.make(
    _gds_klayout_test_impl,
    attrs = {
        "klayout": attr.string(mandatory = True),
    },
    config_settings = {
        str(Label("//:klayout_tool")): str(Label("//:klayout")),
    },
)
