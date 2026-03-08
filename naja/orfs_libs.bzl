"""Module for exposing lib and additional_libs from OrfsInfo and PdkInfo as DefaultInfo files."""

load("//:openroad.bzl", "OrfsInfo", "PdkInfo")

def _orfs_libs_impl(ctx):
    return [DefaultInfo(files = depset(transitive = [
        ctx.attr.src[OrfsInfo].additional_libs,
        ctx.attr.src[PdkInfo].libs,
    ]))]

orfs_libs = rule(
    implementation = _orfs_libs_impl,
    attrs = {
        "src": attr.label(
            mandatory = True,
            providers = [OrfsInfo, PdkInfo],
            doc = "Target with libs",
        ),
    },
    doc = "Exposes lib and additional_libs from OrfsInfo and PdkInfo as DefaultInfo files.",
)
