"""analysistest: a downstream stage's action inputs must include the
files passed via `data =` to its upstream `src =` stage.

Regression coverage for `private/environment.bzl`'s `source_inputs(ctx)`
pulling `ctx.attr.src[OrfsDepInfo].files` into the action's input depset.
Without that propagation, design-private sources from config.mk (e.g.
ADDITIONAL_LEFS from `$(wildcard $(DESIGN_DIR)/lef/*.lef)`) reach only
the stage that consumed them as `ctx.files.data` and silently drop off
the input set for every later stage — klayout / openroad then opens
the LEF path baked into args.mk and fails with errno=2 inside the
sandbox.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _source_input_propagation_test_impl(ctx):
    env = analysistest.begin(ctx)

    expected = ctx.attr.expected_basename
    actions = analysistest.target_actions(env)

    matching = []
    for action in actions:
        for f in action.inputs.to_list():
            if f.basename == expected:
                matching.append((action.mnemonic, f.short_path))
                break

    asserts.true(
        env,
        len(matching) > 0,
        "Expected %s in at least one action's inputs of %s, but none found. " % (
            expected,
            analysistest.target_under_test(env).label,
        ) + "Saw %d actions: %s" % (
            len(actions),
            [a.mnemonic for a in actions],
        ),
    )

    return analysistest.end(env)

source_input_propagation_test = analysistest.make(
    _source_input_propagation_test_impl,
    attrs = {
        "expected_basename": attr.string(
            mandatory = True,
            doc = "Basename that must appear in at least one action's " +
                  "inputs of the target under test.",
        ),
    },
)
