"""Test rule to verify OrfsInfo.lib_pre_layout is forwarded through orfs_macro."""

load("//private:providers.bzl", "OrfsInfo")

def _lib_pre_layout_test_impl(ctx):
    """Extracts lib_pre_layout path at analysis time, asserts at test time."""
    info = ctx.attr.target[OrfsInfo]
    path = info.lib_pre_layout.short_path if info.lib_pre_layout else ""

    runner = ctx.actions.declare_file(ctx.attr.name + "_runner.sh")
    ctx.actions.write(
        output = runner,
        is_executable = True,
        content = """\
#!/bin/sh
if [ -z "{path}" ]; then
    echo "FAIL: {label} has OrfsInfo.lib_pre_layout = None"
    exit 1
fi
echo "PASS: {label} has lib_pre_layout = {path}"
""".format(
            label = ctx.attr.target.label,
            path = path,
        ),
    )

    return [DefaultInfo(
        executable = runner,
        runfiles = ctx.runfiles(),
    )]

lib_pre_layout_test = rule(
    implementation = _lib_pre_layout_test_impl,
    attrs = {
        "target": attr.label(
            mandatory = True,
            providers = [OrfsInfo],
            doc = "Target whose OrfsInfo.lib_pre_layout must be non-None",
        ),
    },
    test = True,
)
