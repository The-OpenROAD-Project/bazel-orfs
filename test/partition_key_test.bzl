"""analysistest: a pinned partition is keyed by its module, not by the list.

With SYNTH_KEEP_MODULES pinned and one partition per kept module, a
partition action is named by its module and reads neither the kept list
nor its index, and its config's SYNTH_KEEP_MODULES is its own module. An
edit to the list then re-runs only the modules whose slice it changes;
before, adding or reordering one name re-synthesized every partition.

A module of SYNTH_KEEP_MODULES that a macro of the flow stands for
(`macros`) has no partition and no canonicalize of its own, and the
slicer is told to stub it. A partition and its slice's canonicalize
read no macro's liberty (`macro_libs`) directly, only the macros its own
slice stages, so a macro reaches the key of no partition that does not
instantiate it.
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
            [
                "partition_%s.v" % module,
                "partition_%s_stat.txt" % module,
                "partition_%s.log" % module,
            ],
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
    slicers = [a for a in actions if a.mnemonic == "VerilogSlice"]
    stagers = {}
    for action in actions:
        if action.mnemonic == "PartitionMacros":
            for f in action.outputs.to_list():
                stagers[f.basename] = action
    for action in partitions:
        module = action.env["SYNTH_PARTITION_MODULE"]
        inputs = [f.basename for f in action.inputs.to_list()]
        for name in ctx.attr.macro_libs:
            asserts.false(env, name in inputs, "%s's partition reads %s, not its staged macros" % (module, name))
        if not ctx.attr.macro_libs:
            continue
        staged = "partition_%s_macros" % module
        asserts.true(env, staged in inputs, "%s's partition lacks %s" % (module, staged))
        stager = stagers.get(staged)
        asserts.true(env, stager != None, "nothing stages %s" % staged)
        if stager:
            asserts.equals(
                env,
                ["partition_%s_slice.v" % module],
                [f.basename for f in stager.inputs.to_list() if f.basename.endswith("_slice.v")],
            )
    for action in actions:
        if not (action.env and action.env.get("MODULE_VERILOG_SLICE")):
            continue
        module = action.env["MODULE_TARGET_NAME"]
        inputs = [f.basename for f in action.inputs.to_list()]
        for name in ctx.attr.macro_libs:
            asserts.false(env, name in inputs, "%s's canonicalize reads %s, not its staged macros" % (module, name))
        if ctx.attr.macro_libs:
            staged = "partition_%s_macros" % module
            asserts.true(env, staged in inputs, "%s's canonicalize lacks %s" % (module, staged))
    for macro in ctx.attr.macros:
        for action in actions:
            asserts.false(
                env,
                bool(action.env) and action.env.get("MODULE_TARGET_NAME") == macro,
                "macro %s is canonicalized: %s" % (macro, action.mnemonic),
            )
        asserts.true(env, slicers != [], "no VerilogSlice action")
        for action in slicers:
            argv = action.argv
            asserts.true(
                env,
                any([argv[i:i + 2] == ["--macro", macro] for i in range(len(argv) - 1)]),
                "the slicer does not stub macro %s: %s" % (macro, argv),
            )
    return analysistest.end(env)

partition_key_test = analysistest.make(
    _impl,
    attrs = {
        "macros": attr.string_list(
            doc = "Modules of SYNTH_KEEP_MODULES a macro of the flow stands for.",
        ),
        "macro_libs": attr.string_list(
            doc = "Liberty files of the flow's macros, which a partition " +
                  "reads only as staged from its slice (partition_macros.py).",
        ),
        "modules": attr.string_list(),
    },
)
