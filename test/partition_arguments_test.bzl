"""analysistest: partition_arguments reach their own partition only.

partition_arguments = {"adder": {"ABC_AREA": "1", "SKIP_EXTRACT_FA": "1"}}
puts both in adder's partition config and in no other action's: not the
other kept modules' partitions, not the top's, not the canonicalize or the
merge.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _impl(ctx):
    env = analysistest.begin(ctx)
    actions = analysistest.target_actions(env)
    expected = json.decode(ctx.attr.expected)
    seen = {}
    for action in actions:
        if action.mnemonic != "FileWrite":
            continue
        for f in action.outputs.to_list():
            if not f.basename.endswith(".analysis.json"):
                continue
            config = json.decode(action.content)
            prefix = "1_synth_partition_"
            module = f.basename[len(prefix):-len(".analysis.json")] if f.basename.startswith(prefix) else None
            wanted = expected.get(module, {})
            for var in ctx.attr.variables:
                asserts.equals(
                    env,
                    wanted.get(var),
                    config.get(var),
                    "%s: %s" % (f.basename, var),
                )
            if module in expected:
                seen[module] = True
    asserts.equals(env, sorted(expected.keys()), sorted(seen.keys()), "partition configs found")
    for action in actions:
        if action.env:
            for var in ctx.attr.variables:
                asserts.false(env, var in action.env, "%s in the env of %s" % (var, action.mnemonic))
    return analysistest.end(env)

partition_arguments_test = analysistest.make(
    _impl,
    attrs = {
        "expected": attr.string(doc = "JSON {module: {variable: value}}"),
        "variables": attr.string_list(),
    },
)
