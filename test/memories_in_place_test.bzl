"""analysistest: a stage of another variant reads the AUTO_MEMORIES views in place.

Every stage reads the views from AUTO_MEMORIES_DIR, which the synthesis
sets to its own results, so a stage whose variant differs from its src's
moves none of them into its own results directory. They used to be moved
with the stage's input, and a view moved twice failed the second mv.
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
    for action in analysistest.target_actions(env):
        for src in _moved_sources(action):
            asserts.false(
                env,
                src.endswith("/memories.json") or src.endswith("/memories"),
                "%s moves %s; the views are read from AUTO_MEMORIES_DIR" % (action.mnemonic, src),
            )
    return analysistest.end(env)

memories_in_place_test = analysistest.make(_impl)
