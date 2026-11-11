"""analysistest: with verilog_slices, a kept module's canonicalize reads its slice.

Each per-module canonicalize reads its own slice of the Verilog and none
of the design's sources, the other slices, the global canonicalize's
RTLIL or the whole design's memories, and finds its slice's memories
itself; each partition reads those. So neither waits on a whole-design
read nor reruns for an edit outside its slice.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _impl(ctx):
    env = analysistest.begin(ctx)
    actions = analysistest.target_actions(env)

    slicers = [a for a in actions if a.mnemonic == "VerilogSlice"]
    asserts.equals(env, 1, len(slicers))
    if slicers:
        asserts.equals(
            env,
            sorted(["partition_%s_slice.v" % m for m in ctx.attr.modules]),
            sorted([f.basename for f in slicers[0].outputs.to_list()]),
        )

    canonicalizes = [a for a in actions if a.env and a.env.get("MODULE_VERILOG_SLICE")]
    asserts.equals(
        env,
        sorted(ctx.attr.modules),
        sorted([a.env["MODULE_TARGET_NAME"] for a in canonicalizes]),
    )
    for action in canonicalizes:
        module = action.env["MODULE_TARGET_NAME"]
        inputs = [f.basename for f in action.inputs.to_list()]
        slices = [f for f in inputs if f.endswith("_slice.v")]
        asserts.equals(env, ["partition_%s_slice.v" % module], slices)
        for name in ["1_1_yosys_canonicalize.rtlil", "memories_inferred.json", "memories.json", "memories"] + ctx.attr.sources:
            asserts.false(env, name in inputs, "%s's canonicalize reads %s" % (module, name))
        asserts.true(
            env,
            "partition_%s_memories" % module in [f.basename for f in action.outputs.to_list()],
            "%s's canonicalize does not find its slice's memories" % module,
        )

    # A partition reads its own slice's memories, never the whole design's.
    partitions = [a for a in actions if a.env and a.env.get("SYNTH_PARTITION_MODULE")]
    asserts.equals(env, sorted(ctx.attr.modules), sorted([a.env["SYNTH_PARTITION_MODULE"] for a in partitions]))
    for action in partitions:
        module = action.env["SYNTH_PARTITION_MODULE"]
        inputs = [f.basename for f in action.inputs.to_list()]
        for name in ["memories.json", "memories", "1_1_yosys_canonicalize.rtlil"]:
            asserts.false(env, name in inputs, "%s's partition reads %s" % (module, name))
        asserts.true(env, "partition_%s_memories" % module in inputs, "%s's partition lacks its memories" % module)

    # The merge waits for the slices' memories to be checked against the
    # whole design's; nothing before it does.
    merges = [a for a in actions if "1_2_yosys.v" in [f.basename for f in a.outputs.to_list()]]
    asserts.equals(env, 1, len(merges))
    if merges:
        asserts.true(env, "slice_memories.ok" in [f.basename for f in merges[0].inputs.to_list()], "the merge does not wait for the memories check")
    return analysistest.end(env)

slices_key_test = analysistest.make(
    _impl,
    attrs = {
        "modules": attr.string_list(),
        "sources": attr.string_list(),
    },
)
