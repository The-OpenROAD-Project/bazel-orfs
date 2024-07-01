def _escape(str):
    return str.replace("/", "\\/")

def _replace(original, replacement):
    if len(original) != len(replacement):
        replacement += "\\x0"
    original = _escape(original[:len(replacement)])
    replacement = _escape(replacement)
    return "/".join(["s", original, replacement, "g"])

def _stringpatch_binary_impl(ctx):
    args = ctx.actions.args()
    for k, v in ctx.attr.replacements.items():
        args.add("--expression", _replace(k, ctx.expand_location(v, ctx.attr.data)))
        if len(ctx.expand_location(v, ctx.attr.data)) > len(k):
            fail("Replacement must be shorter than original.")

    out = ctx.actions.declare_file(ctx.attr.name)
    ctx.actions.run_shell(
        inputs = [ctx.file.src],
        arguments = [args, ctx.file.src.path],
        command = "sed $@ > {}".format(out.path),
        outputs = [out],
        mnemonic = "StringPatch",
    )

    return [DefaultInfo(
        executable = out,
        files = depset([out]),
        runfiles = ctx.attr.src[DefaultInfo].default_runfiles,
    )]

stringpatch_binary = rule(
    implementation = _stringpatch_binary_impl,
    attrs = {
        "data": attr.label_list(
            doc = "List of labels to be referred to from \"replacements\".",
            allow_files = True,
            default = [],
        ),
        "replacements": attr.string_dict(),
        "src": attr.label(mandatory = True, allow_single_file = True),
    },
    provides = [DefaultInfo],
    executable = True,
)
