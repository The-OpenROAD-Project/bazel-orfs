"""analysistest: a stage of another variant moves each input once.

A stage whose variant differs from its src's moves the src's results
into its own results directory before make runs. When the src is the
synthesis, its files already carry the AUTO_MEMORIES views
(memories.json, memories/), and OrfsInfo.memories carried them again:
the second mv found the file gone, and the stage failed with

    mv: cannot stat '.../memories.json': No such file or directory
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _moved_sources(action):
    moved = []
    for arg in action.argv or []:
        flat = arg.replace(";", " ").replace("&&", " ").replace("\n", " ")
        tokens = [t for t in flat.split(" ") if t]
        for i, token in enumerate(tokens[:-1]):
            if token != "mv":
                continue
            src = [t for t in tokens[i + 1:] if not t.startswith("-")]
            if src:
                moved.append(src[0])
    return moved

def _impl(ctx):
    env = analysistest.begin(ctx)
    found = False
    for action in analysistest.target_actions(env):
        moved = _moved_sources(action)
        seen = {}
        for src in moved:
            asserts.false(
                env,
                src in seen,
                "%s moves %s twice" % (action.mnemonic, src),
            )
            seen[src] = True
            if src.endswith("/memories.json"):
                found = True
    asserts.true(
        env,
        found,
        "no action moves the synthesis's memories.json; the fixture no " +
        "longer exercises a variant on a shared AUTO_MEMORIES synthesis",
    )
    return analysistest.end(env)

variant_move_once_test = analysistest.make(_impl)
