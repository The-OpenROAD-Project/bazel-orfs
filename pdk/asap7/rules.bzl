"""Starlark rule to recompress .lib.7z files from @asap7sc7p5t_28 to .lib.gz."""

def _un7z_gz_impl(ctx):
    ctx.actions.run(
        executable = ctx.executable._tool,
        arguments = [ctx.file.src.path, ctx.outputs.out.path],
        inputs = [ctx.file.src],
        outputs = [ctx.outputs.out],
        mnemonic = "Un7zGz",
        progress_message = "Recompressing %{input} -> %{output}",
    )
    return [DefaultInfo(files = depset([ctx.outputs.out]))]

un7z_gz = rule(
    implementation = _un7z_gz_impl,
    attrs = {
        "src": attr.label(
            allow_single_file = [".7z"],
            mandatory = True,
        ),
        "out": attr.output(
            mandatory = True,
        ),
        "_tool": attr.label(
            cfg = "exec",
            default = Label("//pdk/asap7:un7z_gz_bin"),
            executable = True,
        ),
    },
)
