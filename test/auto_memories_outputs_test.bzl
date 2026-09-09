"""analysistest: AUTO_MEMORIES declares its generated views as outputs.

ORFS's AUTO_MEMORIES writes results/memories.json and a
results/memories/ directory of generated .lib/.lef views during
canonicalization, and every later stage reads them back by globbing the
results dir (load.tcl, read_liberty.tcl). In a sandbox only declared
outputs survive, so if the synth rule does not declare them the views
are discarded the moment canonicalization ends and floorplan fails to
link the blackboxed memory modules.

The negative half matters as much as the positive one: a design without
AUTO_MEMORIES must declare neither, or every design in the world pays
for a directory artifact and a JSON it never produces -- and the action
would fail for not creating them.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _output_basenames(env):
    names = {}
    for action in analysistest.target_actions(env):
        for f in action.outputs.to_list():
            names[f.basename] = action.mnemonic
    return names

def _auto_memories_outputs_test_impl(ctx):
    env = analysistest.begin(ctx)
    declared = _output_basenames(env)
    label = analysistest.target_under_test(env).label

    for name in ctx.attr.expected:
        asserts.true(
            env,
            name in declared,
            ("Expected %s among the declared outputs of %s, but it is " +
             "absent. Declared: %s") % (name, label, sorted(declared)),
        )

    for name in ctx.attr.forbidden:
        asserts.true(
            env,
            name not in declared,
            ("%s is declared as an output of %s, which does not set " +
             "AUTO_MEMORIES=1. Nothing produces it, so the action would " +
             "fail for not creating it.") % (name, label),
        )

    return analysistest.end(env)

auto_memories_outputs_test = analysistest.make(
    _auto_memories_outputs_test_impl,
    attrs = {
        "expected": attr.string_list(
            doc = "Output basenames that must be declared.",
        ),
        "forbidden": attr.string_list(
            doc = "Output basenames that must NOT be declared.",
        ),
    },
)
