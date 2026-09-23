"""analysistest: the mock pin knobs reach the mocked variant only.

MOCK_AREA_PIN_EDGES and MOCK_AREA_PIN_MARGIN are read by mock_area.tcl and
mock_pins.tcl for a mock_area = "pins" flow's mocked variant. The real flow
never reads them; carried in its arguments, they became part of its
floorplan action's key, and every block re-floorplanned, re-placed and
re-abstracted whenever a parent changed the margin.

Scans the target's actions (argv, env and written content, which holds
the stage's config.mk) for the variable's name.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _mentions(action, needle):
    for arg in action.argv or []:
        if needle in arg:
            return True
    for k, v in (action.env or {}).items():
        if needle in k or needle in v:
            return True

    # Only a FileWrite's content is the text the rule wrote (the stage's
    # config.mk is one); asking another action for it makes bazel read its
    # template or target from disk, which at analysis time may not exist.
    return action.mnemonic == "FileWrite" and needle in action.content

def _mock_pin_knobs_test_impl(ctx):
    env = analysistest.begin(ctx)
    needle = ctx.attr.variable
    hits = [a.mnemonic for a in analysistest.target_actions(env) if _mentions(a, needle)]
    label = analysistest.target_under_test(env).label
    if ctx.attr.expect_present:
        asserts.true(env, len(hits) > 0, "%s: expected %s in an action, found none" % (label, needle))
    else:
        asserts.true(env, len(hits) == 0, "%s: %s must not reach this target, found in %s" % (label, needle, hits))
    return analysistest.end(env)

mock_pin_knobs_test = analysistest.make(
    _mock_pin_knobs_test_impl,
    attrs = {
        "expect_present": attr.bool(mandatory = True),
        "variable": attr.string(default = "MOCK_AREA_PIN_MARGIN"),
    },
)
