"""analysistest: a pinned partition is keyed by its module, not by the list.

With SYNTH_KEEP_MODULES pinned and one partition per kept module, a
partition action is named by its module and reads neither the kept list
nor its index, and its config's SYNTH_KEEP_MODULES is its own module. An
edit to the list then re-runs only the modules whose slice it changes;
before, adding or reordering one name re-synthesized every partition.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _impl(ctx):
    env = analysistest.begin(ctx)
    actions = analysistest.target_actions(env)
    partitions = [a for a in actions if a.env and a.env.get("SYNTH_PARTITION_MODULE")]
    asserts.equals(
        env,
        sorted(ctx.attr.modules),
        sorted([a.env["SYNTH_PARTITION_MODULE"] for a in partitions]),
    )
    for action in partitions:
        module = action.env["SYNTH_PARTITION_MODULE"]
        for var in ["SYNTH_PARTITION_ID", "SYNTH_NUM_PARTITIONS"]:
            asserts.false(env, var in action.env, "%s's partition has %s" % (module, var))
        inputs = [f.basename for f in action.inputs.to_list()]
        for name in ["kept_modules.json", "1_synth.mk"]:
            asserts.false(env, name in inputs, "%s's partition reads %s" % (module, name))
        asserts.equals(
            env,
            ["partition_%s.v" % module],
            [f.basename for f in action.outputs.to_list()],
        )

    configs = {}
    for action in actions:
        for f in action.outputs.to_list():
            if f.basename.startswith("1_synth_partition_") and f.basename.endswith(".analysis.json"):
                configs[f.basename] = json.decode(action.content)
    for module in ctx.attr.modules:
        config = configs.get("1_synth_partition_%s.analysis.json" % module)
        asserts.true(env, config != None, "no config for %s's partition" % module)
        if config == None:
            continue
        flat = json.encode(config)
        asserts.true(
            env,
            '"SYNTH_KEEP_MODULES":"%s"' % module in flat,
            "%s's config keeps other modules: %s" % (module, flat),
        )
        asserts.false(
            env,
            "SYNTH_NUM_PARTITIONS" in flat,
            "%s's config carries SYNTH_NUM_PARTITIONS" % module,
        )
    return analysistest.end(env)

partition_key_test = analysistest.make(
    _impl,
    attrs = {"modules": attr.string_list()},
)
