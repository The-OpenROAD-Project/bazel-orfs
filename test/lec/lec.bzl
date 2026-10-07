"""Rules for kepler-formal LEC (Logic Equivalence Checking).

Generates a config file from template, runs kepler-formal, and
reports pass/fail as a Bazel test.

kepler-formal operates on Verilog netlists and checks combinational
equivalence. Sequential boundary changes are not supported.

Requirements for the input Verilog:
  - No change of sequential boundaries between gold and gate.
  - No change in names of hierarchical instances, sequential instances,
    and top terminals.
"""

def _lec_test_impl(ctx):
    # Generate kepler-formal YAML config
    config = ctx.actions.declare_file(ctx.attr.name + ".yaml")
    ctx.actions.expand_template(
        template = ctx.file._config_template,
        output = config,
        substitutions = {
            "${GOLD}": "\n  - ".join(
                [""] + [file.short_path for file in ctx.files.gold_verilog_files],
            ),
            "${GATE}": "\n  - ".join(
                [""] + [file.short_path for file in ctx.files.gate_verilog_files],
            ),
            "${LIBERTY}": "\n  - ".join(
                [""] + [file.short_path for file in ctx.files.liberty_files],
            ) if ctx.files.liberty_files else "",
            "${LOG_LEVEL}": ctx.attr.log_level,
        },
    )

    script = ctx.actions.declare_file(ctx.attr.name + ".run.sh")
    ctx.actions.write(
        script,
        content = """#!/bin/bash
set -euo pipefail

# kepler-formal reads both designs with one frontend: -verilog for gate
# netlists (cells from the liberty files), -sv for SystemVerilog RTL.

gold_files="{gold_files}"
gate_files="{gate_files}"
liberty_files="{liberty_files}"

# kepler-formal's exit status does not say whether the designs differ
# (0 for a combinational difference); its verdict is the line it logs,
# worded per mode, and the test passes only on the expected one.
log="${{TEST_UNDECLARED_OUTPUTS_DIR:-.}}/kepler-formal.log"
{kepler_formal} -{frontend} {verification}{boundary}{gated}--design1 $gold_files --design2 $gate_files \
    ${{liberty_files:+--liberty $liberty_files}} 2>&1 | tee "$log" || true
# The miter's own log (solver start, size and finish) is a file of its
# own beside the run; keep it with the test's outputs.
cp miter_log_*.txt "${{TEST_UNDECLARED_OUTPUTS_DIR:-.}}/" 2>/dev/null || true
grep -qE "{verdict}" "$log"
{size_check}{gated_check}""".format(
            kepler_formal = ctx.executable._kepler_formal.short_path,
            boundary = "--allow-boundary-mismatch " if ctx.attr.allow_boundary_mismatch else "",
            gated = "--skip-gated-clock-flops --report-skipped-pos " if ctx.attr.skip_gated_clock_flops else "",
            # The skip must have happened, and its list stays with the
            # test's outputs: what was left out is part of the verdict.
            gated_check = (
                'cp skipped_gated_clock_pos.txt "${TEST_UNDECLARED_OUTPUTS_DIR:-.}/" 2>/dev/null || true\n' +
                'grep -q "skip_gated_clock_flops (experimental): [0-9]* flop" "$log"\n'
            ) if ctx.attr.skip_gated_clock_flops else "",
            frontend = ctx.attr.frontend,
            size_check = 'grep -qE "Starting solver: [0-9]+ variables, [0-9]+ clauses" miter_log_*.txt\n' if ctx.attr.expect_problem_size else "",
            # kepler-formal checks SystemVerilog input sequentially only.
            verification = "-v sec " if ctx.attr.frontend == "sv" else "",
            verdict = "No (binary-defined )?difference was found" if ctx.attr.expect_equivalent else "\\] Difference was found",
            gold_files = " ".join(
                [file.short_path for file in ctx.files.gold_verilog_files],
            ),
            gate_files = " ".join(
                [file.short_path for file in ctx.files.gate_verilog_files],
            ),
            liberty_files = " ".join(
                [file.short_path for file in ctx.files.liberty_files],
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
                            config,
                            ctx.executable._kepler_formal,
                        ] +
                        ctx.files.gold_verilog_files +
                        ctx.files.gate_verilog_files +
                        ctx.files.liberty_files,
                transitive_files = depset(
                    transitive = [
                        ctx.attr._kepler_formal[DefaultInfo].default_runfiles.files,
                    ],
                ),
            ),
        ),
    ]

_lec_test = rule(
    implementation = _lec_test_impl,
    doc = """Logic equivalence checking test using kepler-formal.

    Compares gold (reference) and gate (modified) Verilog netlists for
    combinational equivalence. Fails the test if any mismatch is found.
    """,
    attrs = {
        "gold_verilog_files": attr.label_list(
            doc = "Gold (reference) Verilog files.",
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "gate_verilog_files": attr.label_list(
            doc = "Gate (modified) Verilog files.",
            allow_files = True,
            providers = [DefaultInfo],
        ),
        "liberty_files": attr.label_list(
            doc = "Liberty (.lib) files for cell definitions. Optional for RTL-to-RTL checks.",
            allow_files = True,
            providers = [DefaultInfo],
            default = [],
        ),
        "frontend": attr.string(
            doc = "kepler-formal's reader: verilog for gate netlists (with liberty_files), sv for SystemVerilog RTL.",
            default = "verilog",
            values = ["verilog", "sv"],
        ),
        "expect_problem_size": attr.bool(
            doc = "Also require the solver's problem-size line (patches/kepler-formal-0001); combinational LEC only.",
            default = False,
        ),
        "allow_boundary_mismatch": attr.bool(
            doc = "Compare designs whose sequential boundaries differ (a flop one side lacks) instead of stopping on it.",
            default = False,
        ),
        "expect_equivalent": attr.bool(
            doc = "False for a test that proves a difference is caught.",
            default = True,
        ),
        "skip_gated_clock_flops": attr.bool(
            doc = "Experimental (patches/kepler-formal-0002): leave out the next state of every flop clocked through a cell kepler-formal cannot model, an integrated clock gate, with a warning listing them, and compare the rest.",
            default = False,
        ),
        "log_level": attr.string(
            doc = "Log verbosity: debug, info, warning, error.",
            default = "info",
        ),
        "_kepler_formal": attr.label(
            doc = "kepler-formal binary.",
            executable = True,
            allow_files = True,
            cfg = "exec",
            default = Label("@kepler-formal//src/bin:kepler-formal"),
        ),
        "_config_template": attr.label(
            default = "//test/lec:lec.yaml.tpl",
            allow_single_file = True,
        ),
    },
    test = True,
)

def lec_test(name, tags = [], **kwargs):
    """A kepler-formal LEC test, always `manual`.

    kepler-formal is a dev_dependency that builds from source, too slow
    for CI. Run a check by name: `bazelisk test //path:name`.

    Args:
        name: the test's name.
        tags: extra tags; `manual` is always added.
        **kwargs: the attributes of the rule (gold_verilog_files,
            gate_verilog_files, liberty_files, log_level).
    """
    _lec_test(
        name = name,
        tags = tags + ([] if "manual" in tags else ["manual"]),
        **kwargs
    )
