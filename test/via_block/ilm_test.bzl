"""The interface-logic-model targets orfs_flow makes (private/ilm.bzl)."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts", "unittest")
load("//private:ilm.bzl", "ilm_blocks", "ilm_read_stage")

def _read_stage_test(ctx):
    env = unittest.begin(ctx)
    for stop, start, squash, want in [
        (None, "synth", False, "grt"),
        ("final", "synth", False, "grt"),
        ("route", "synth", False, "grt"),
        ("grt", "synth", False, "grt"),
        ("cts", "synth", False, "cts"),
        ("place", "synth", False, "place"),
        ("floorplan", "synth", False, None),
        ("synth", "synth", False, None),
        ("cts", "cts", False, "cts"),
        ("cts", "grt", False, None),
        ("cts", "floorplan", True, "cts"),
        ("final", "floorplan", True, None),
    ]:
        asserts.equals(
            env,
            want,
            ilm_read_stage(stop, start, squash),
            "stop %s, start %s, squash %s" % (stop, start, squash),
        )
    return unittest.end(env)

def _blocks_test(ctx):
    env = unittest.begin(ctx)
    asserts.equals(env, [], ilm_blocks([]), "no macros, no blocks")
    asserts.equals(
        env,
        [],
        ilm_blocks(["//sram:fakeram7_64x21", ":gds_scope_macro"]),
        "a macro that is no flow's abstract is timed by its liberty",
    )
    asserts.equals(
        env,
        [
            (":BlockA_generate_abstract", ":BlockA_ilm_part"),
            ("//x:alu_fast_generate_abstract", "//x:alu_fast_ilm_part"),
        ],
        ilm_blocks([":BlockA_generate_abstract", "//sram:fakeram7_64x21", "//x:alu_fast_generate_abstract"]),
        "each flow abstract beside its interface logic model, variant included",
    )
    return unittest.end(env)

read_stage_test = unittest.make(_read_stage_test)
blocks_test = unittest.make(_blocks_test)

def ilm_unit_test_suite(name):
    unittest.suite(name, read_stage_test, blocks_test)

def _ilm_sta_inputs_test_impl(ctx):
    env = analysistest.begin(ctx)
    actions = [a for a in analysistest.target_actions(env) if a.mnemonic == "IlmSta"]
    asserts.equals(env, 1, len(actions), "one OpenSTA run")
    if len(actions) != 1:
        return analysistest.end(env)
    inputs = [f.short_path for f in actions[0].inputs.to_list()]
    pkg = ctx.attr.target_under_test.label.package
    for part in ctx.attr.parts:
        for f in ["part.v", "part.spef", "part.sdc", "part_libs.tar"]:
            path = "%s/%s/%s" % (pkg, part, f)
            asserts.true(env, path in inputs, "%s reads %s" % (ctx.attr.target_under_test.label, path))
    command = actions[0].argv[-1]
    asserts.true(
        env,
        "STA_PARTS='%s'" % ctx.attr.modules in command,
        "the parent, then each block by its module: %s" % ctx.attr.modules,
    )
    asserts.true(env, "STA_WIRES=%s" % ctx.attr.wires in command, "STA_WIRES=%s" % ctx.attr.wires)
    return analysistest.end(env)

ilm_sta_inputs_test = analysistest.make(
    _ilm_sta_inputs_test_impl,
    attrs = {
        "modules": attr.string(),
        "parts": attr.string_list(),
        "wires": attr.string(),
    },
)

def _part_stage_test_impl(ctx):
    env = analysistest.begin(ctx)
    runs = [a for a in analysistest.target_actions(env) if a.env.get("PART_STAGE")]
    asserts.equals(env, 1, len(runs), "one sta_part.tcl run")
    if len(runs) == 1:
        asserts.equals(env, ctx.attr.stage, runs[0].env["PART_STAGE"], "the stage read")
        asserts.equals(env, ctx.attr.ilm, runs[0].env["STA_ILM"], "interface logic only")
    return analysistest.end(env)

ilm_part_stage_test = analysistest.make(
    _part_stage_test_impl,
    attrs = {
        "ilm": attr.string(),
        "stage": attr.string(),
    },
)

def _absent_test_impl(ctx):
    script = ctx.actions.declare_file(ctx.attr.name + ".sh")
    present = ctx.attr.present
    ctx.actions.write(
        script,
        "#!/bin/sh\n" + (
            "echo 'made, and should not be: %s'\nexit 1\n" % " ".join(present) if present else "exit 0\n"
        ),
        is_executable = True,
    )
    return [DefaultInfo(executable = script)]

_absent_test = rule(
    implementation = _absent_test_impl,
    attrs = {"present": attr.string_list()},
    test = True,
)

def ilm_absent_test(name, targets):
    """Fails if any of `targets`, names in this package, exists.

    Args:
        name: the test.
        targets: target names that should not be made.
    """
    _absent_test(
        name = name,
        present = [t for t in targets if native.existing_rule(t)],
    )
