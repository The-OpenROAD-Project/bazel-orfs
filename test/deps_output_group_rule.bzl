"""Test rule to verify an ORFS stage target's deps reproducer tarball."""

def _deps_tar_test_impl(ctx):
    """Verifies a stage target's deps output group holds a valid tarball."""
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
# Verify it contains a config.mk (proves _package_stage ran correctly).
if ! tar -tf "$TARBALL" | grep -q 'config\\.mk'; then
    echo "FAIL: tarball missing config.mk"
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
            doc = "A filegroup of an ORFS stage target's deps output group",
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

def _deps_groups_test_impl(ctx):
    """The //:deps output groups, checked at analysis: deps_scripts is
    the four small files `next` installs, and deps_inputs leaves out the
    earlier stage's results that deps_files carries."""
    info = ctx.attr.target[OutputGroupInfo]
    scripts = info.deps_scripts.to_list()
    names = sorted([f.basename for f in scripts])
    if len(scripts) != 4:
        fail("deps_scripts of {} has {} files, want 4 (manifest, make wrapper, config, make): {}".format(
            ctx.attr.target.label,
            len(scripts),
            names,
        ))
    for f in scripts:
        if f.basename.endswith(".odb") or f.basename.endswith(".v"):
            fail("deps_scripts of {} carries a stage output: {}".format(ctx.attr.target.label, f.path))
    files = [f.basename for f in info.deps_files.to_list()]
    inputs = [f.basename for f in info.deps_inputs.to_list()]
    for r in ctx.attr.results:
        if r not in files:
            fail("deps_files of {} lacks the earlier result {}".format(ctx.attr.target.label, r))
        if r in inputs:
            fail("deps_inputs of {} carries the earlier result {}: `next` would build it".format(ctx.attr.target.label, r))
    runner = ctx.actions.declare_file(ctx.attr.name + ".sh")
    ctx.actions.write(runner, "#!/bin/sh\necho 'PASS: checked at analysis'\n", is_executable = True)
    return [DefaultInfo(executable = runner)]

deps_groups_test = rule(
    implementation = _deps_groups_test_impl,
    attrs = {
        "results": attr.string_list(doc = "Basenames of the earlier stage's results."),
        "target": attr.label(mandatory = True, doc = "An ORFS stage target."),
    },
    test = True,
)
