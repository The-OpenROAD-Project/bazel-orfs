"""scaled_macro_lib: bundle two scaled .lib files into an OrfsInfo provider.

orfs_macro() forwards lib_pre_layout from its `lib` attribute's OrfsInfo
provider (see private/rules.bzl:_macro_impl). A plain file label carries no
such provider, so handing orfs_macro() bare .lib files would silently drop
the dual-characterization (propagated-clock post-CTS .lib + ideal-clock
pre-layout .lib). This rule exists to rebuild the provider around the two
scaled files emitted by the memory_macro_scaler genrule.
"""

load("//private:providers.bzl", "OrfsInfo")

def _scaled_lib_impl(ctx):
    return [
        DefaultInfo(files = depset([ctx.file.lib])),
        OrfsInfo(
            odb = None,
            gds = None,
            lef = None,
            lib = ctx.file.lib,
            lib_pre_layout = ctx.file.lib_pre_layout,
            additional_gds = depset(),
            additional_lefs = depset(),
            additional_libs = depset(),
            additional_libs_pre_layout = depset(),
            arguments = depset(),
        ),
    ]

scaled_macro_lib = rule(
    implementation = _scaled_lib_impl,
    attrs = {
        "lib": attr.label(
            allow_single_file = [".lib"],
            mandatory = True,
            doc = "Scaled post-CTS (propagated-clock) Liberty file.",
        ),
        "lib_pre_layout": attr.label(
            allow_single_file = [".lib"],
            mandatory = True,
            doc = "Scaled pre-layout (ideal-clock) Liberty file.",
        ),
    },
    provides = [DefaultInfo, OrfsInfo],
)
