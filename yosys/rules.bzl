"""Rules for the yosys module."""

def _extract_share_impl(ctx):
    """Extract yosys share directory from tar into a tree artifact."""
    share = ctx.actions.declare_directory("share")
    ctx.actions.run_shell(
        inputs = [ctx.file.tar],
        outputs = [share],
        command = "tar -xf {tar} -C {out} --strip-components=1".format(
            tar = ctx.file.tar.path,
            out = share.path,
        ),
    )
    return [DefaultInfo(files = depset([share]))]

extract_share = rule(
    implementation = _extract_share_impl,
    attrs = {
        "tar": attr.label(
            mandatory = True,
            allow_single_file = [".tar"],
        ),
    },
)
