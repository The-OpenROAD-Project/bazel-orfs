"""Test rule to verify deps pkg_tar on ORFS stage targets."""

def _deps_tar_test_impl(ctx):
    """Verifies an ORFS stage target has a valid _deps pkg_tar companion."""
    deps_files = ctx.attr.target[DefaultInfo].files.to_list()
    if not deps_files:
        fail("Target {} has no output files".format(ctx.attr.target.label))

    tarballs = [f for f in deps_files if f.basename.endswith(".tar.gz") or f.basename.endswith(".tar")]
    if not tarballs:
        fail("Target {} has no tarball".format(ctx.attr.target.label))
    tarball = tarballs[0]

    runner = ctx.actions.declare_file(ctx.attr.name + "_runner.sh")
    ctx.actions.write(
        output = runner,
        is_executable = True,
        content = """\
#!/bin/sh
set -e
RUNFILES="${{RUNFILES_DIR:-$0.runfiles}}"
TARBALL="$RUNFILES/_main/{path}"
if [ ! -f "$TARBALL" ]; then
    echo "FAIL: tarball not found: $TARBALL"
    exit 1
fi
# Verify it contains a deploy manifest.
if ! tar -tf "$TARBALL" | grep -q '_deploy_manifest\\.txt'; then
    echo "FAIL: tarball missing deploy manifest"
    exit 1
fi
echo "PASS: {label} deps tarball is valid"
""".format(
            path = tarball.short_path,
            label = ctx.attr.target.label,
        ),
    )

    return [DefaultInfo(
        executable = runner,
        runfiles = ctx.runfiles(files = [tarball]),
    )]

deps_output_group_test = rule(
    implementation = _deps_tar_test_impl,
    attrs = {
        "target": attr.label(
            mandatory = True,
            doc = "ORFS stage _deps pkg_tar target to validate",
        ),
    },
    test = True,
)

def _output_group_test_impl(ctx):
    """Verifies a named output group exists and contains files."""
    group_name = ctx.attr.output_group
    info = ctx.attr.target[OutputGroupInfo]

    group = getattr(info, group_name, None)
    if group == None:
        fail("Target {} has no '{}' output group".format(
            ctx.attr.target.label,
            group_name,
        ))

    files = group.to_list()
    if not files:
        fail("Output group '{}' on {} is empty".format(
            group_name,
            ctx.attr.target.label,
        ))

    runner = ctx.actions.declare_file(ctx.attr.name + "_runner.sh")
    ctx.actions.write(
        output = runner,
        is_executable = True,
        content = """\
#!/bin/sh
echo "PASS: {label} has output group '{group}' with {count} file(s)"
""".format(
            label = ctx.attr.target.label,
            group = group_name,
            count = len(files),
        ),
    )

    return [DefaultInfo(
        executable = runner,
        runfiles = ctx.runfiles(files = files),
    )]

output_group_test = rule(
    implementation = _output_group_test_impl,
    attrs = {
        "target": attr.label(
            mandatory = True,
            doc = "Target to check for the named output group",
        ),
        "output_group": attr.string(
            mandatory = True,
            doc = "Name of the output group to verify",
        ),
    },
    test = True,
)
