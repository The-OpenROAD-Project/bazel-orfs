"""
This module defines rules for working with Scala toolchains.
"""

load("//toolchains/scala:scala_toolchain_info.bzl", "ArgsListInfo", "ToolConfigInfo")

def _scala_toolchain_impl(ctx):
    return [
        platform_common.ToolchainInfo(
            args = ctx.attr.args,
            tool_map = ctx.attr.tool_map,
            runfiles = ctx.runfiles(
                files = ctx.files._runtime,
                transitive_files = ctx.toolchains["@bazel_tools//tools/jdk:toolchain_type"].java.java_runtime.files,
            ),
        ),
    ]

scala_toolchain = rule(
    doc = "Define a scala toolchain.",
    implementation = _scala_toolchain_impl,
    attrs = {
        "args": attr.label_list(providers = [ArgsListInfo]),
        "tool_map": attr.label(providers = [ToolConfigInfo], mandatory = True),
        "_runtime": attr.label_list(
            default = [
                Label("@maven//:org_scala_lang_scala_library"),
                Label("@maven//:org_scala_lang_scala_reflect"),
            ],
        ),
    },
    toolchains = [
        "@bazel_tools//tools/jdk:toolchain_type",
    ],
)
