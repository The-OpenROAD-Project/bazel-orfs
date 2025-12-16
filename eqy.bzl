"""Rules for eqy"""

def _eqy_test_impl(ctx):
    eqy = ctx.actions.declare_file(ctx.attr.name + ".eqy")
    ctx.actions.expand_template(
        template = ctx.file._eqy_template,
        output = eqy,
        substitutions = {
            "${DEPTH}": str(ctx.attr.depth),
            "${GATE}": " ".join(
                [file.short_path for file in ctx.files.gate_verilog_files],
            ),
            "${GOLD}": " ".join(
                [file.short_path for file in ctx.files.gold_verilog_files],
            ),
            "${TOP}": ctx.attr.module_top,
        },
    )

    script = ctx.actions.declare_file(ctx.attr.name + ".run.sh")
    ctx.actions.write(
        script,
        content = """
# !/bin/sh
set -euo pipefail
test_status=0
(exec {eqy} "$@" {eqy_script}) || test_status=$?

if [ $test_status -ne 0 ]; then
    echo "Copying $(find {results_folder} . | wc -l) files to bazel-testlogs/$(dirname $TEST_BINARY)/{results_folder}/test.outputs for inspection."
    cp -r {results_folder} $TEST_UNDECLARED_OUTPUTS_DIR/
    gold_verilog_files="{gold_verilog_files}"
    gate_verilog_files="{gate_verilog_files}"
    for kind in gold_verilog_files gate_verilog_files; do
        for f in ${{!kind}}; do
            dest=$(echo "$f" | sed 's|^\\.\\./|external/|')
            mkdir -p "$TEST_UNDECLARED_OUTPUTS_DIR/$kind/$(dirname "$dest")"
            cp --parents "$f" "$TEST_UNDECLARED_OUTPUTS_DIR/$kind/"
        done
    done
    exit $test_status
fi
""".format(
            eqy = ctx.executable._eqy.short_path,
            eqy_script = eqy.short_path,
            results_folder = ctx.attr.name,
            gold_verilog_files = " ".join(
                [file.short_path for file in ctx.files.gold_verilog_files],
            ),
            gate_verilog_files = " ".join(
                [file.short_path for file in ctx.files.gate_verilog_files],
            ),
        ),
        is_executable = True,
    )

    return [
        DefaultInfo(
            files = depset([script]),
            executable = script,
            runfiles = ctx.runfiles(
                files = [
                            eqy,
                            ctx.executable._eqy,
                            ctx.executable._yosys,
                            ctx.executable._yosys_smtbmc,
                        ] +
                        ctx.files.gate_verilog_files +
                        ctx.files.gold_verilog_files,
                transitive_files = depset(
                    transitive = [
                        ctx.attr._eqy[DefaultInfo].default_runfiles.files,
                        ctx.attr._eqy[DefaultInfo].default_runfiles.symlinks,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.files,
                        ctx.attr._yosys[DefaultInfo].default_runfiles.symlinks,
                        ctx.attr._yosys_smtbmc[DefaultInfo].default_runfiles.files,
                        ctx.attr._yosys_smtbmc[DefaultInfo].default_runfiles.symlinks,
                    ],
                ),
            ),
        ),
    ]

eqy_test = rule(
    implementation = _eqy_test_impl,
    attrs = {
        "depth": attr.int(mandatory = True),
        "gate_verilog_files": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "gold_verilog_files": attr.label_list(
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "module_top": attr.string(mandatory = True),
        "_eqy": attr.label(
            doc = "Eqy binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@oss_cad_suite//:eqy"),
        ),
        "_eqy_template": attr.label(
            default = "eqy.tpl",
            allow_single_file = True,
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
    },
    test = True,
)
