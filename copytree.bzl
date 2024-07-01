def _copytree_impl(ctx):
    outs = []

    for f in ctx.files.srcs:
        prefix = "/".join([f.owner.workspace_root, ctx.attr.strip_prefix.strip("/")])
        _, _, after = f.path.partition(prefix)
        if not after:
            continue

        out = ctx.actions.declare_file(after.strip("/"))
        ctx.actions.symlink(output = out, target_file = f)
        outs.append(out)

    return [DefaultInfo(
        files = depset(outs),
    )]

copytree = rule(
    implementation = _copytree_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = True),
        "strip_prefix": attr.string(),
    },
    provides = [DefaultInfo],
    executable = False,
)
