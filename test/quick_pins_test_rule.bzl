"""Test rule: assert a stage target carries a named file as a data dep.

Used to verify that orfs_flow(quick_pins=True) injects quick_pins.tcl as
PRE_GLOBAL_PLACE_SKIP_IO_TCL and quick_pins_footprint_stub.tcl as
FOOTPRINT_TCL. Walks `data_runfiles` of the target, looking for the
expected basenames; failure means the source wiring in flow.bzl was lost.
"""

def _quick_pins_data_dep_test_impl(ctx):
    expected = sorted(ctx.attr.expected_basenames)
    runfiles = ctx.attr.target[DefaultInfo].data_runfiles
    names = sorted([f.basename for f in runfiles.files.to_list()])
    missing = [b for b in expected if b not in names]

    runner = ctx.actions.declare_file(ctx.attr.name + "_runner.sh")
    ctx.actions.write(
        output = runner,
        is_executable = True,
        content = """\
#!/bin/sh
EXPECTED='{expected}'
MISSING='{missing}'
if [ -n "$MISSING" ]; then
    echo "FAIL: {label} data_runfiles missing: $MISSING"
    echo "      (expected: $EXPECTED)"
    exit 1
fi
echo "PASS: {label} data_runfiles include: $EXPECTED"
""".format(
            label = ctx.attr.target.label,
            expected = " ".join(expected),
            missing = " ".join(missing),
        ),
    )

    return [DefaultInfo(
        executable = runner,
        runfiles = ctx.runfiles(),
    )]

quick_pins_data_dep_test = rule(
    implementation = _quick_pins_data_dep_test_impl,
    attrs = {
        "target": attr.label(
            mandatory = True,
            doc = "Stage target whose data_runfiles must contain the basenames",
        ),
        "expected_basenames": attr.string_list(
            mandatory = True,
            doc = "Basenames expected to appear in target.data_runfiles",
        ),
    },
    test = True,
)
