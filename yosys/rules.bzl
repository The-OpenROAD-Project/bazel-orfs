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

def _cc_files_impl(ctx):
    """Extract raw header and library files from a cc_library for genrule use."""
    cc_info = ctx.attr.dep[CcInfo]
    headers = cc_info.compilation_context.headers.to_list()
    default_files = ctx.attr.dep[DefaultInfo].files.to_list()
    return [DefaultInfo(files = depset(headers + default_files))]

cc_files = rule(
    implementation = _cc_files_impl,
    attrs = {
        "dep": attr.label(mandatory = True, providers = [CcInfo]),
    },
)
