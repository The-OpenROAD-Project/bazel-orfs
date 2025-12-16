"""Yosys rules"""

def _yosys_impl(ctx):
    outs = []
    for k in dir(ctx.outputs):
        outs.extend(getattr(ctx.outputs, k))

    ctx.actions.run(
        arguments = [
            ctx.expand_location(arg, ctx.attr.srcs)
            for arg in ctx.attr.arguments
        ],
        executable = ctx.executable._yosys,
        inputs = depset(
            ctx.files.srcs +
            [
                ctx.executable._yosys,
            ],
            transitive = [
                ctx.attr._yosys[DefaultInfo].default_runfiles.files,
                ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
            ],
        ),
        outputs = outs,
    )

    return [
        DefaultInfo(
            files = depset(outs),
        ),
    ]

yosys = rule(
    implementation = _yosys_impl,
    attrs = {
        "arguments": attr.string_list(
            mandatory = True,
        ),
        "outs": attr.output_list(
            mandatory = True,
        ),
        "srcs": attr.label_list(
            mandatory = True,
            allow_files = True,
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@docker_orfs//:yosys"),
        ),
    },
    provides = [DefaultInfo],
)
