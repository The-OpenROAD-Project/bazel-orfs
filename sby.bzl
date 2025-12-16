"""Rules for sby"""

load("//:generate.bzl", "fir_library")
load("//:verilog.bzl", "verilog_directory", "verilog_single_file_library")

def _sby_test_impl(ctx):
    sby = ctx.actions.declare_file(ctx.attr.name + ".sby")

    ctx.actions.expand_template(
        template = ctx.file._sby_template,
        output = sby,
        substitutions = {
            "${TOP}": ctx.attr.module_top,
            "${VERILOG_BASE_NAMES}": " ".join(
                [file.basename for file in ctx.files.verilog_files],
            ),
            "${VERILOG}": "\n".join(
                [file.short_path for file in ctx.files.verilog_files],
            ),
        },
    )

    script = ctx.actions.declare_file(ctx.attr.name + ".run.sh")
    ctx.actions.write(
        script,
        content = """
# !/bin/sh
echo "Files found in $(pwd)"
exec {} "$@" {}

""".format(
            ctx.executable._sby.short_path,
            sby.short_path,
        ),
        is_executable = True,
    )

    return [
        DefaultInfo(
            files = depset([script]),
            executable = script,
            runfiles = ctx.runfiles(
                files = [sby, ctx.executable._sby, ctx.executable._yosys] +
                        ctx.files.verilog_files,
                transitive_files = depset(
                    transitive = [
                        ctx.attr._sby[DefaultInfo].default_runfiles.files,
                        ctx.attr._sby[DefaultInfo].default_runfiles.symlinks,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.files,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
                    ],
                ),
            ),
        ),
    ]

_sby_test = rule(
    implementation = _sby_test_impl,
    attrs = {
        "module_top": attr.string(mandatory = True),
        "verilog_files": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "_sby": attr.label(
            doc = "sby binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:sby"),
        ),
        "_sby_template": attr.label(
            default = "sby.tpl",
            allow_single_file = True,
        ),
        "_yosys": attr.label(
            doc = "Yosys binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:yosys"),
        ),
    },
    test = True,
)

def sby_test(
        name,
        module_top,
        generator,
        generator_opts = [],
        verilog_files = [],
        **kwargs):
    """sby_test macro frontend to run formal verification with sby.

    Args:
        name: Name of the test target.
        module_top: Top module name in the verilog files.
        generator: Label of the scala binary that generates the verilog files.
        generator_opts: List of options passed to Generator scala app for generating the verilog.
        verilog_files: List of additional verilog files to include in the sby test.
        **kwargs: Additional args passed to _sby_test.
    """

    # massage output for sby
    firtool_options = [
        "--disable-all-randomization",
        "-strip-debug-info",
        "-disable-layers=Verification",
        "-disable-layers=Verification.Assert",
        "-disable-layers=Verification.Assume",
        "-disable-layers=Verification.Cover",
    ]

    fir_library(
        name = "{name}_fir".format(name = name),
        data = [],
        generator = generator,
        opts = generator_opts + firtool_options,
        tags = ["manual"],
    )

    # FIXME we have to split the files or we get the verification layer stubs
    # https://github.com/llvm/circt/issues/9020
    verilog_directory(
        name = "{name}_split".format(name = name),
        srcs = [":{name}_fir".format(name = name)],
        opts = firtool_options,
        tags = ["manual"],
    )

    # And concat the files into one again for sby
    verilog_single_file_library(
        name = "{name}.sv".format(name = name),
        srcs = [":{name}_split".format(name = name)],
        tags = ["manual"],
        visibility = ["//visibility:public"],
    )

    _sby_test(
        name = name + "_test",
        module_top = module_top,
        verilog_files = verilog_files + [":{name}.sv".format(name = name)],
        **kwargs
    )
