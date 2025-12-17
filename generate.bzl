"""
fir_library rule for generating FIR files from source files using a specified generator tool.
"""

# buildifier: disable=module-docstring

def _fir_library_impl(ctx):
    fir = ctx.actions.declare_file(ctx.attr.name + ".fir")

    args = ctx.actions.args()
    args.add_all([ctx.expand_location(opt, ctx.attr.data) for opt in ctx.attr.opts])
    args.add("-o", fir)
    ctx.actions.run(
        arguments = [args],
        executable = ctx.executable.generator,
        env = {
            "CHISEL_FIRTOOL_PATH": ctx.executable._firtool.dirname,
        },
        inputs = [
                     ctx.executable.generator,
                     ctx.executable._firtool,
                 ] +
                 ctx.files.data,
        outputs = [fir],
        mnemonic = "FirGeneration",
    )
    return [
        DefaultInfo(
            runfiles = ctx.runfiles(files = []),
            files = depset([fir]),
        ),
    ]

fir_library = rule(
    implementation = _fir_library_impl,
    attrs = {
        "data": attr.label_list(
            allow_files = True,
        ),
        "generator": attr.label(
            cfg = "exec",
            executable = True,
            mandatory = True,
        ),
        "opts": attr.string_list(default = []),
        "_firtool": attr.label(
            doc = "Firtool binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@circt//:bin/firtool"),
        ),
    },
)
