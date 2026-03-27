"""Test rule to verify deps output group on ORFS stage targets."""

def _deps_output_group_test_impl(ctx):
    """Verifies an ORFS stage target has a valid deps output group.

    The deps output group should contain a deploy script that only depends
    on cheap actions (config write, template expansion), not the main
    make action. This test verifies the output group exists and the
    deploy script looks correct.
    """
    deps_files = ctx.attr.target[OutputGroupInfo].deps.to_list()
    if not deps_files:
        fail("Target {} has no 'deps' output group".format(ctx.attr.target.label))

    deploy_script = deps_files[0]

    runner = ctx.actions.declare_file(ctx.attr.name + "_runner.sh")
    ctx.actions.write(
        output = runner,
        is_executable = True,
        content = """\
#!/bin/sh
set -e
RUNFILES="${{RUNFILES_DIR:-$0.runfiles}}"
DEPLOY_SCRIPT="$RUNFILES/_main/{path}"
if [ ! -f "$DEPLOY_SCRIPT" ]; then
    echo "FAIL: deploy script not found: $DEPLOY_SCRIPT"
    exit 1
fi
if ! head -1 "$DEPLOY_SCRIPT" | grep -q '#!/usr/bin/env bash'; then
    echo "FAIL: deploy script missing shebang"
    exit 1
fi
if ! grep -q 'config.mk' "$DEPLOY_SCRIPT"; then
    echo "FAIL: deploy script missing config.mk reference"
    exit 1
fi
echo "PASS: {label} deps output group is valid"
""".format(
            path = deploy_script.short_path,
            label = ctx.attr.target.label,
        ),
    )

    return [DefaultInfo(
        executable = runner,
        runfiles = ctx.runfiles(files = [deploy_script]),
    )]

deps_output_group_test = rule(
    implementation = _deps_output_group_test_impl,
    attrs = {
        "target": attr.label(
            mandatory = True,
            doc = "ORFS stage target to check for deps output group",
        ),
    },
    test = True,
)
