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

Declaring them is necessary and not sufficient, which is the other half
of this file. The views have to reach the action that reads them back,
and for a long time they did not: the serial synthesis path carried
them into the ODB action and the parallel path did not, so every design
with SYNTH_NUM_PARTITIONS set -- the default -- generated correct macro
views, discarded them at the sandbox boundary, and failed with

    [ERROR ORD-2013] instance <inst> LEF master <memory> not found

`consumed_by` asserts the other end of that, and names the reader: the
action that produces 1_synth.odb is the one that globs the views back
out of the results dir, so it is the one that has to be handed them. An
earlier form of this assertion only asked whether *some* action consumed
them, which the partition actions satisfied on their own -- it passed
with the ODB action still unfed.

Its coverage is honest but partial, and the gap is worth naming: the
only design in reach with AUTO_MEMORIES=1 is asap7/tinyRocket, which
does not set SYNTH_HIERARCHICAL and therefore takes the serial path --
the one that was always correct. Catching the parallel-path regression
in this file needs a design that sets both, and there is none here yet.
A design that does exercise it is what found the bug, and adding a
minimal one is worth doing separately.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _output_basenames(env):
    names = {}
    for action in analysistest.target_actions(env):
        for f in action.outputs.to_list():
            names[f.basename] = action.mnemonic
    return names

def _inputs_of_producer(env, output_basename):
    """Input basenames of the action that produces `output_basename`.

    None if no action produces it. "Some action consumes the artifact"
    is too weak an assertion to be worth making: the artifact can be
    staged into one action and missing from another that reads it, which
    is exactly the shape of the bug this file exists to catch.
    """
    for action in analysistest.target_actions(env):
        for f in action.outputs.to_list():
            if f.basename == output_basename:
                return {i.basename: True for i in action.inputs.to_list()}
    return None

def _argv_of_producer(env, output_basename):
    """Command line of the action that produces `output_basename`, or None."""
    for action in analysistest.target_actions(env):
        for f in action.outputs.to_list():
            if f.basename == output_basename:
                return action.argv
    return None

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

    for output, required in ctx.attr.consumed_by.items():
        inputs = _inputs_of_producer(env, output)
        asserts.true(
            env,
            inputs != None,
            "no action of %s produces %s" % (label, output),
        )
        for name in (inputs != None and required or []):
            asserts.true(
                env,
                name in inputs,
                ("the action producing %s in %s does not take %s as an " +
                 "input. Only declared outputs survive a sandbox, and only " +
                 "staged inputs reach the action that reads them -- a stage " +
                 "that globs this out of the results dir will find " +
                 "nothing.") % (output, label, name),
            )

    for output, staged in ctx.attr.old_file.items():
        argv = _argv_of_producer(env, output)
        asserts.true(
            env,
            argv != None,
            "no action of %s produces %s" % (label, output),
        )
        for name in (argv != None and staged or []):
            asserts.true(
                env,
                any([a.startswith("--old-file=") and a.endswith("/" + name) for a in argv]),
                ("the action producing %s in %s does not pass --old-file " +
                 "for %s. A staged artifact carries whatever mtime the " +
                 "cache or the sandbox gave it, and make reads an older " +
                 "one as a reason to remake it here, where VERILOG_FILES " +
                 "is empty.") % (output, label, name),
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
        "consumed_by": attr.string_list_dict(
            doc = "Maps an output basename to the input basenames the " +
                  "action producing it must consume. Asserting that the " +
                  "reader is given them, rather than that somebody is.",
        ),
        "old_file": attr.string_list_dict(
            doc = "Maps an output basename to the staged input basenames " +
                  "the action producing it must name in a --old-file " +
                  "switch, so make takes them as up to date whatever " +
                  "their timestamps say.",
        ),
        "forbidden": attr.string_list(
            doc = "Output basenames that must NOT be declared.",
        ),
    },
)
