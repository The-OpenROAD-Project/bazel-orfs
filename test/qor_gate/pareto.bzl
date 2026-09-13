"""A Pareto-front score for a pull request, as a bazel test.

One design cannot tell a signal from a draw, so a per-design Pareto check
is not a verdict. This wires several designs into one: each vehicle's
`metadata.json` is compared against a committed baseline by
`check_pareto.py`, and `fleet.py` reduces the per-design verdicts using
the two-witness rule measured in the study (bazel-orfs #981).

The test is `manual` because every vehicle runs an ORFS flow. What makes
that affordable is the choice of vehicles, not the choice of stages: the
study measured that detection depends on how many designs you run and
almost not at all on how big they are, so the vehicles here are the
smallest designs that still span the PDKs.
"""

def _metadata_of(target):
    """The metadata.json a generate_metadata stage produced."""
    for f in target[DefaultInfo].files.to_list():
        if f.basename == "metadata.json":
            return f
    fail("target {} produced no metadata.json; is it a generate_metadata stage?".format(
        target.label,
    ))

def _pareto_front_test_impl(ctx):
    if len(ctx.attr.vehicles) != len(ctx.files.baselines):
        fail("each vehicle needs exactly one baseline, in the same order")

    inputs = [ctx.file._check_pareto, ctx.file._fleet]
    lines = [
        "#!/bin/sh",
        "set -u",
        'R="${RUNFILES_DIR:-$0.runfiles}/_main"',
        'W="${TEST_TMPDIR:-/tmp}"',
        "rc=0",
        "verdicts=''",
    ]

    for vehicle, baseline in zip(ctx.attr.vehicles, ctx.files.baselines):
        metadata = _metadata_of(vehicle)
        inputs.append(metadata)
        name = vehicle.label.name
        lines += [
            'echo "--- {}"'.format(name),
            # A vehicle that cannot be scored must not silently vanish from
            # the fleet: a missing verdict would shrink the witness count
            # and could turn a resolved regression into did-not-resolve.
            'python3 "$R/{cp}" --metadata "$R/{md}" --baseline "$R/{bl}" \\'.format(
                cp = ctx.file._check_pareto.short_path,
                md = metadata.short_path,
                bl = baseline.short_path,
            ),
            '    --json "$W/{}.pareto.json" || rc=$?'.format(name),
            'if [ ! -f "$W/{n}.pareto.json" ]; then'.format(n = name),
            '  echo "FAIL: {} produced no verdict at all"; exit 1'.format(name),
            "fi",
            'verdicts="$verdicts $W/{}.pareto.json"'.format(name),
        ]
        inputs.append(baseline)

    lines += [
        "echo",
        # check_pareto exits non-zero per design; that is per-design news,
        # not the fleet verdict, so its status is deliberately discarded
        # here and the fleet score decides.
        'python3 "$R/{fleet}" $verdicts --witnesses {w} --fail-on "{f}"'.format(
            fleet = ctx.file._fleet.short_path,
            w = ctx.attr.witnesses,
            f = ctx.attr.fail_on,
        ),
    ]

    runner = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(runner, "\n".join(lines) + "\n", is_executable = True)
    return [DefaultInfo(
        executable = runner,
        runfiles = ctx.runfiles(files = inputs),
    )]

pareto_front_test = rule(
    implementation = _pareto_front_test_impl,
    doc = "Score a change against the QoR Pareto front across several designs.",
    attrs = {
        "vehicles": attr.label_list(
            mandatory = True,
            doc = "generate_metadata stage targets, one per design.",
        ),
        "baselines": attr.label_list(
            allow_files = True,
            mandatory = True,
            doc = "Committed metadata.json per vehicle, same order. A measured " +
                  "baseline is preferred over rules-base.json golden values: " +
                  "both arms are then from the same toolchain on the same day.",
        ),
        "witnesses": attr.int(
            default = 2,
            doc = "Designs that must agree before an axis counts as moved. " +
                  "One is a draw; the study measured 98.4% median direction " +
                  "concordance for real tool changes.",
        ),
        "fail_on": attr.string(
            default = "worse",
            doc = "Verdicts that fail the test. A trade is a legitimate pull " +
                  "request, and did-not-resolve is a statement about the " +
                  "instrument rather than about the change.",
        ),
        "_check_pareto": attr.label(
            default = "//:check_pareto.py",
            allow_single_file = True,
        ),
        "_fleet": attr.label(
            default = "//test/qor_gate:fleet.py",
            allow_single_file = True,
        ),
    },
    test = True,
)
