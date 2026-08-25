"""analysistest: pin down which synth actions see the raw SDC.

The expensive yosys actions (canonicalize, do-yosys, keep, partitions)
read only the extracted clock period (SDC_FILE_CLOCK_PERIOD ->
results/clock_period.txt, ORFS's do-sdc-clock-period target), never the
raw SDC — so a period-preserving SDC edit re-runs only the cheap
extraction and sdc-copy actions, not synthesis. These tests key on the
action that produces a named output and assert which basenames must and
must not appear among its inputs, locking that split in place.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _synth_action_inputs_test_impl(ctx):
    env = analysistest.begin(ctx)

    actions = analysistest.target_actions(env)
    matching = []
    for action in actions:
        for out in action.outputs.to_list():
            if out.basename == ctx.attr.output_basename:
                matching.append(action)
                break

    asserts.equals(
        env,
        1,
        len(matching),
        "Expected exactly one action of %s producing %s, found %d" % (
            analysistest.target_under_test(env).label,
            ctx.attr.output_basename,
            len(matching),
        ),
    )

    for action in matching:
        input_basenames = {f.basename: True for f in action.inputs.to_list()}
        for required in ctx.attr.required_input_basenames:
            asserts.true(
                env,
                required in input_basenames,
                "Expected %s in the inputs of the action producing %s" % (
                    required,
                    ctx.attr.output_basename,
                ),
            )
        for forbidden in ctx.attr.forbidden_input_basenames:
            asserts.false(
                env,
                forbidden in input_basenames,
                "Expected %s NOT to be an input of the action producing %s" % (
                    forbidden,
                    ctx.attr.output_basename,
                ),
            )

    return analysistest.end(env)

synth_action_inputs_test = analysistest.make(
    _synth_action_inputs_test_impl,
    attrs = {
        "output_basename": attr.string(
            mandatory = True,
            doc = "Selects the action under test: the (single) action " +
                  "producing an output with this basename.",
        ),
        "required_input_basenames": attr.string_list(
            doc = "Basenames that must appear among the selected " +
                  "action's inputs.",
        ),
        "forbidden_input_basenames": attr.string_list(
            doc = "Basenames that must NOT appear among the selected " +
                  "action's inputs.",
        ),
    },
)
