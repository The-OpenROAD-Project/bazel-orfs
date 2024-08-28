def _eqy_test_impl(ctx):
    eqy = ctx.actions.declare_file(ctx.attr.name + ".eqy")
    ctx.actions.expand_template(
        template = ctx.file._eqy_template,
        output = eqy,
        substitutions = {
            "${DEPTH}": str(ctx.attr.depth),
            "${GATE}": " ".join([file.short_path for file in ctx.files.gate_verilog_files]),
            "${GOLD}": " ".join([file.short_path for file in ctx.files.gold_verilog_files]),
            "${TOP}": ctx.attr.module_top,
        },
    )

    script = ctx.actions.declare_file(ctx.attr.name + ".run.sh")
    ctx.actions.write(script, content = """
# !/bin/sh
exec {} "$@" {}

""".format(ctx.executable._eqy.short_path, eqy.short_path), is_executable = True)

    return [
        DefaultInfo(
            files = depset([script]),
            executable = script,
            runfiles = ctx.runfiles(
                files =
                    [eqy, ctx.executable._eqy, ctx.executable._yosys, ctx.executable._yosys_smtbmc] + ctx.files.gate_verilog_files + ctx.files.gold_verilog_files,
                transitive_files =
                    depset(transitive = [
                        ctx.attr._eqy[DefaultInfo].default_runfiles.files,
                        ctx.attr._eqy[DefaultInfo].default_runfiles.symlinks,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.files,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
                        ctx.attr._yosys_smtbmc[DefaultInfo].default_runfiles.files,
                        ctx.attr._yosys_smtbmc[DefaultInfo].default_runfiles.symlinks,
                    ]),
            ),
        ),
    ]

eqy_test = rule(
    implementation = _eqy_test_impl,
    attrs = {
        "gate_verilog_files": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "gold_verilog_files": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "module_top": attr.string(mandatory = True),
        "depth": attr.int(mandatory = True),
        "_eqy": attr.label(
            doc = "Eqy binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:eqy"),
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:yosys"),
        ),
        "_yosys_smtbmc": attr.label(
            doc = "Yosys smtbmc binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:yosys_smtbmc"),
        ),
        "_eqy_template": attr.label(
            default = "eqy.tpl",
            allow_single_file = True,
        ),
    },
    test = True,
)
