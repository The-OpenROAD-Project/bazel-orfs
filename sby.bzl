"""Rules for sby formal verification."""

load("//:generate.bzl", "fir_library")
load("//:verilog.bzl", "verilog_directory", "verilog_single_file_library")

# Default firtool options for formal verification.
#
# firtool is invoked twice in this flow — first by the Chisel generator
# (fir_library, via CHISEL_FIRTOOL_PATH) to lower CHIRRTL, then by
# verilog_directory to produce SystemVerilog. These options must be
# passed to both passes to stay consistent.
#
# Verification.Assert is kept enabled so that DUT-internal Chisel
# assert() statements are checked by the formal solver. The layer bind
# files use `include directives which are stripped by
# verilog_single_file_library (see verilog.bzl).
#
# Assume and Cover are disabled: assumes would over-constrain the
# solver and covers are not needed for BMC.
DEFAULT_FIRTOOL_OPTIONS = [
    "--disable-all-randomization",
    "-strip-debug-info",
    "-disable-layers=Verification.Assume",
    "-disable-layers=Verification.Cover",
]

def _sby_test_impl(ctx):
    sby = ctx.actions.declare_file(ctx.attr.name + ".sby")

    ctx.actions.expand_template(
        template = ctx.file._sby_template,
        output = sby,
        substitutions = {
            "${DEPTH}": str(ctx.attr.depth),
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
#!/bin/sh
echo "Files found in $(pwd)"
{sby} "$@" {sby_file}
rc=$?
# Copy counterexample traces to test outputs so they survive sandbox cleanup
if [ -n "$TEST_UNDECLARED_OUTPUTS_DIR" ]; then
    for f in $(find . -name "trace.vcd" -o -name "trace_tb.v" -o -name "trace.yw" 2>/dev/null); do
        dir="$TEST_UNDECLARED_OUTPUTS_DIR/$(dirname "$f")"
        mkdir -p "$dir"
        cp "$f" "$dir/"
    done
fi
exit $rc
""".format(
            sby = ctx.executable._sby.short_path,
            sby_file = sby.short_path,
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
        "depth": attr.int(mandatory = True),
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
        depth = 20,
        generator_opts = [],
        firtool_options = None,
        verilog_files = [],
        **kwargs):
    """Run SymbiYosys bounded model checking on a Chisel-generated design.

    Generates Verilog from Chisel source, then runs SymbiYosys BMC with
    the bitwuzla solver. Additional SystemVerilog files (formal wrappers
    with SVA properties) can be included via verilog_files.

    Args:
        name: Name of the test target. The actual test will be name + "_test".
        module_top: Top module name for formal checking (typically the
            formal wrapper module, e.g. "FormalMyModule").
        generator: Label of the Chisel generator binary (scala_binary that
            calls chisel3.stage.ChiselStage).
        depth: BMC depth — number of clock cycles to unroll. Higher values
            find deeper bugs but take exponentially longer. Default 20.
        generator_opts: Options passed to the Chisel generator binary
            (e.g. ["--top-module=my.package.MyModule"]).
        firtool_options: Options passed to firtool for both CHIRRTL lowering
            and Verilog generation. Defaults to DEFAULT_FIRTOOL_OPTIONS which
            disables randomization and Verification layers. Override to
            customize layer handling or add other firtool flags.
        verilog_files: Additional SystemVerilog files to include (e.g. formal
            wrapper files with SVA properties using `ifdef FORMAL).
        **kwargs: Additional args passed to the underlying test rule
            (e.g. tags, timeout, size).
    """
    if firtool_options == None:
        firtool_options = DEFAULT_FIRTOOL_OPTIONS

    fir_library(
        name = "{name}_fir".format(name = name),
        data = [],
        generator = generator,
        opts = generator_opts + firtool_options,
        tags = ["manual"],
    )

    # Split into per-module files to avoid verification layer stubs
    # https://github.com/llvm/circt/issues/9020
    verilog_directory(
        name = "{name}_split".format(name = name),
        srcs = [":{name}_fir".format(name = name)],
        opts = firtool_options,
        tags = ["manual"],
    )

    # Concat back into a single file for sby
    verilog_single_file_library(
        name = "{name}.sv".format(name = name),
        srcs = [":{name}_split".format(name = name)],
        tags = ["manual"],
        visibility = ["//visibility:public"],
    )

    _sby_test(
        name = name + "_test",
        depth = depth,
        module_top = module_top,
        verilog_files = verilog_files + [":{name}.sv".format(name = name)],
        **kwargs
    )
