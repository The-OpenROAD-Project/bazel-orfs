"""analysistest: every action that runs yosys finds Tcl's script library.

yosys links Tcl without its script library, so without TCL_LIBRARY Tcl_Init
finds no init.tcl and each run in Tcl mode warns "Tcl_Init() call failed".
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _impl(ctx):
    env = analysistest.begin(ctx)
    yosys = [
        a
        for a in analysistest.target_actions(env)
        if a.env and "YOSYS_EXE" in a.env and a.env["YOSYS_EXE"] in [f.path for f in a.inputs.to_list()]
    ]
    asserts.true(env, len(yosys) > 0, "the fixture runs no yosys action")
    for action in yosys:
        lib = action.env.get("TCL_LIBRARY", "")
        asserts.true(env, lib.endswith("/library"), "%s: TCL_LIBRARY is %r" % (action.mnemonic, lib))
        inputs = [f.path for f in action.inputs.to_list()]
        asserts.true(
            env,
            lib + "/init.tcl" in inputs,
            "%s does not stage %s/init.tcl" % (action.mnemonic, lib),
        )
    return analysistest.end(env)

yosys_tcl_library_test = analysistest.make(_impl)
