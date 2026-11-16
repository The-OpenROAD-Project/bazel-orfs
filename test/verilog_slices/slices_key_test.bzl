"""analysistest: with verilog_slices, a kept module's canonicalize reads its slice.

Each per-module canonicalize, the top's included, reads its own slice of
the Verilog and none of the design's sources, the other slices, the
global canonicalize's RTLIL or the whole design's memories, and finds its
slice's memories itself; each partition, the top's included, reads
those. So neither waits on a whole-design read nor reruns for an edit
outside its slice. The design's memories, which the merge's 1_synth.odb
reads, are the slices' union.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _impl(ctx):
    env = analysistest.begin(ctx)
    actions = analysistest.target_actions(env)

    sliced = ctx.attr.modules + [ctx.attr.top]
    slicers = [a for a in actions if a.mnemonic == "VerilogSlice"]
    asserts.equals(env, 1, len(slicers))
    if slicers:
        asserts.equals(
            env,
            sorted(["partition_%s_slice.v" % m for m in sliced]),
            sorted([f.basename for f in slicers[0].outputs.to_list()]),
        )

    canonicalizes = [a for a in actions if a.env and a.env.get("MODULE_VERILOG_SLICE")]
    asserts.equals(
        env,
        sorted(sliced),
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

    # The top partition reads the top's slice, not the global canonicalize.
    tops = [a for a in actions if a.env and a.env.get("SYNTH_PARTITION_ID") == "top"]
    asserts.equals(env, 1, len(tops))
    for action in tops:
        inputs = [f.basename for f in action.inputs.to_list()]
        for name in ["1_1_yosys_canonicalize.rtlil", "memories.json", "memories_inferred.json", "memories"] + ctx.attr.sources:
            asserts.false(env, name in inputs, "the top partition reads %s" % name)
        for name in ["partition_%s_slice.rtlil", "partition_%s_memories"]:
            asserts.true(env, name % ctx.attr.top in inputs, "the top partition lacks " + name % ctx.attr.top)

    # The design's memories are the union of the slices'. Neither the
    # merge nor 1_synth.odb reads anything the whole design's
    # canonicalize and memory detection write; the check that holds the
    # union to that detection is a validation action, off their path.
    def producing(name):
        return [a for a in actions if name in [f.basename for f in a.outputs.to_list()]]

    canons = producing("1_1_yosys_canonicalize.rtlil")
    unions = producing("memories.json")
    asserts.equals(env, 1, len(canons))
    asserts.equals(env, 1, len(unions))
    if canons and unions:
        whole = canons[0].outputs.to_list()
        asserts.true(env, "memories_whole_design" in [f.basename for f in whole])
        asserts.equals(env, "SliceMemoriesUnion", unions[0].mnemonic)
        asserts.equals(
            env,
            sorted(["partition_%s_memories" % m for m in sliced]),
            sorted([f.basename for f in unions[0].inputs.to_list() if f.basename.endswith("_memories")]),
        )
        union = unions[0].outputs.to_list()
        for name in ["1_2_yosys.v", "1_synth.odb"]:
            readers = producing(name)
            asserts.equals(env, 1, len(readers), name)
            for reader in readers:
                inputs = reader.inputs.to_list()
                for f in whole:
                    asserts.false(env, f in inputs, "%s waits for %s" % (name, f.basename))
                if name == "1_synth.odb":
                    for f in union:
                        asserts.true(env, f in inputs, "%s lacks the union's %s" % (name, f.basename))
    validation = analysistest.target_under_test(env)[OutputGroupInfo]._validation.to_list()
    asserts.equals(env, ["slice_memories.ok"], [f.basename for f in validation])
    return analysistest.end(env)

slices_key_test = analysistest.make(
    _impl,
    attrs = {
        "modules": attr.string_list(),
        "sources": attr.string_list(),
        "top": attr.string(),
    },
)

def _grouped_impl(ctx):
    env = analysistest.begin(ctx)
    actions = analysistest.target_actions(env)

    # A partition of several kept modules reads each one's slice's
    # memories, and neither the whole design's nor another partition's.
    partitions = [
        a
        for a in actions
        if a.env and a.env.get("SYNTH_PARTITION_ID") not in [None, "top"]
    ]
    asserts.equals(env, sorted(ctx.attr.partitions.keys()), sorted([a.env["SYNTH_PARTITION_ID"] for a in partitions]))
    for action in partitions:
        i = action.env["SYNTH_PARTITION_ID"]
        asserts.equals(env, "1", action.env.get("SYNTH_SLICE_MEMORIES"), "partition %s" % i)
        inputs = [f.basename for f in action.inputs.to_list()]
        for name in ["memories.json", "memories_inferred.json", "memories", "1_1_yosys_canonicalize.rtlil"]:
            asserts.false(env, name in inputs, "partition %s reads %s" % (i, name))
        asserts.equals(
            env,
            sorted(["partition_%s_memories" % m for m in ctx.attr.partitions[i]]),
            sorted([f for f in inputs if f.endswith("_memories")]),
            "partition %s" % i,
        )
    return analysistest.end(env)

slices_grouped_test = analysistest.make(
    _grouped_impl,
    attrs = {
        "partitions": attr.string_list_dict(),
    },
)

def _off_impl(ctx):
    env = analysistest.begin(ctx)
    actions = analysistest.target_actions(env)
    asserts.equals(env, [], [a.mnemonic for a in actions if a.mnemonic == "VerilogSlice"])
    asserts.equals(env, [], [
        a.env["MODULE_TARGET_NAME"]
        for a in actions
        if a.env and a.env.get("MODULE_VERILOG_SLICE")
    ])
    return analysistest.end(env)

slices_off_test = analysistest.make(_off_impl)

def _floorplan_impl(ctx):
    env = analysistest.begin(ctx)
    actions = analysistest.target_actions(env)

    # With slices the floorplan neither reads nor forwards the whole
    # design's canonicalize; without them it does both, as before.
    canon = "1_1_yosys_canonicalize.rtlil"
    floorplans = [
        a
        for a in actions
        if "2_floorplan.odb" in [f.basename for f in a.outputs.to_list()]
    ]
    asserts.equals(env, 1, len(floorplans))
    for action in floorplans:
        inputs = [f.basename for f in action.inputs.to_list()]
        asserts.equals(env, ctx.attr.canonicalize, canon in inputs, "the floorplan reads %s" % canon)
    files = analysistest.target_under_test(env)[DefaultInfo].files.to_list()
    asserts.equals(env, ctx.attr.canonicalize, canon in [f.basename for f in files], "the floorplan forwards %s" % canon)
    return analysistest.end(env)

slices_floorplan_test = analysistest.make(
    _floorplan_impl,
    attrs = {
        "canonicalize": attr.bool(mandatory = True),
    },
)
