"""analysistest: with verilog_slices, a kept module's canonicalize reads its slice.

Each per-module canonicalize reads its own slice of the Verilog and none
of the design's sources, the other slices or the global canonicalize's
RTLIL, so it neither waits on the global canonicalize nor reruns for an
edit outside its slice.
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
        for name in ["1_1_yosys_canonicalize.rtlil", "memories_inferred.json"] + ctx.attr.sources:
            asserts.false(env, name in inputs, "%s's canonicalize reads %s" % (module, name))
    return analysistest.end(env)

slices_key_test = analysistest.make(
    _impl,
    attrs = {
        "modules": attr.string_list(),
        "sources": attr.string_list(),
    },
)
