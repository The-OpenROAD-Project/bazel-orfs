"""analysistest: which macro views a flow's arguments name.

Keys on the FileWrite action that writes a named arguments .json (e.g.
1_synth.analysis.json) and asserts which basenames each listed variable
must and must not name.
"""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _basenames(value):
    return {path.split("/")[-1]: True for path in value.split(" ") if path}

def _macro_arguments_test_impl(ctx):
    env = analysistest.begin(ctx)
    label = analysistest.target_under_test(env).label
    contents = [
        action.content
        for action in analysistest.target_actions(env)
        if action.mnemonic == "FileWrite" and
           [f for f in action.outputs.to_list() if f.basename == ctx.attr.output_basename]
    ]
    asserts.equals(
        env,
        1,
        len(contents),
        "%s: expected one FileWrite of %s, found %d" % (label, ctx.attr.output_basename, len(contents)),
    )
    if len(contents) != 1:
        return analysistest.end(env)
    arguments = json.decode(contents[0])
    for variable, basenames in ctx.attr.required.items():
        names = _basenames(arguments.get(variable, ""))
        for basename in basenames:
            asserts.true(
                env,
                basename in names,
                "%s: %s does not name %s: %s" % (label, variable, basename, sorted(names)),
            )
    for variable, basenames in ctx.attr.forbidden.items():
        names = _basenames(arguments.get(variable, ""))
        for basename in basenames:
            asserts.false(
                env,
                basename in names,
                "%s: %s names %s" % (label, variable, basename),
            )
    return analysistest.end(env)

macro_arguments_test = analysistest.make(
    _macro_arguments_test_impl,
    attrs = {
        "forbidden": attr.string_list_dict(
            doc = "Variable to basenames it must not name.",
        ),
        "output_basename": attr.string(
            mandatory = True,
            doc = "The arguments .json the FileWrite under test writes.",
        ),
        "required": attr.string_list_dict(
            doc = "Variable to basenames it must name.",
        ),
    },
)
