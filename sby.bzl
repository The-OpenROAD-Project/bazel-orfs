"""Rules for sby"""

def _sby_test_impl(ctx):
    sby = ctx.actions.declare_file(ctx.attr.name + ".sby")

    ctx.actions.expand_template(
        template = ctx.file._sby_template,
        output = sby,
        substitutions = {
            "${VERILOG_BASE_NAMES}": " ".join([file.basename for file in ctx.files.verilog_files]),
            "${VERILOG}": " ".join([file.short_path for file in ctx.files.verilog_files]),
            "${TOP}": ctx.attr.module_top,
        },
    )

    script = ctx.actions.declare_file(ctx.attr.name + ".run.sh")
    ctx.actions.write(script, content = """
# !/bin/sh
echo "Files found in $(pwd)"
exec {} "$@" {}

""".format(ctx.executable._sby.short_path, sby.short_path), is_executable = True)

    return [
        DefaultInfo(
            files = depset([script]),
            executable = script,
            runfiles = ctx.runfiles(
                files =
                    [sby, ctx.executable._sby, ctx.executable._yosys] + ctx.files.verilog_files,
                transitive_files =
                    depset(transitive = [
                        ctx.attr._sby[DefaultInfo].default_runfiles.files,
                        ctx.attr._sby[DefaultInfo].default_runfiles.symlinks,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.files,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
                    ]),
            ),
        ),
    ]

sby_test = rule(
    implementation = _sby_test_impl,
    attrs = {
        "verilog_files": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "module_top": attr.string(mandatory = True),
        "_sby": attr.label(
            doc = "sby binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:sby"),
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:yosys"),
        ),
        "_sby_template": attr.label(
            default = "sby.tpl",
            allow_single_file = True,
        ),
    },
    test = True,
)
