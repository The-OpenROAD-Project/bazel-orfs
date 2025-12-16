"""Implementation of scala_tool"""

load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("//toolchains/scala/impl:collect.bzl", "collect_data")

def _scala_tool_impl(ctx):
    exe_info = ctx.attr.src[DefaultInfo]
    if exe_info.files_to_run != None and exe_info.files_to_run.executable != None:
        exe = exe_info.files_to_run.executable
    elif len(exe_info.files.to_list()) == 1:
        exe = exe_info.files.to_list()[0]
    else:
        fail(
            "Expected scala_tool's src attribute to be either an executable or a single file",
        )

    runfiles = collect_data(ctx, ctx.attr.data + [ctx.attr.src])
    link = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(
        output = link,
        target_file = exe,
        is_executable = True,
    )
    return [
        p
        for p in [
            ctx.attr.src[JavaInfo] if JavaInfo in ctx.attr.src else None,
            DefaultInfo(
                files = depset([link]),
                runfiles = runfiles,
                executable = link,
            ),
        ]
        if p
    ]

scala_tool = rule(
    implementation = _scala_tool_impl,
    # @unsorted-dict-items
    attrs = {
        "src": attr.label(
            allow_files = True,
            cfg = "exec",
            executable = True,
            doc = """The underlying binary that this tool represents.

Usually just a single prebuilt (eg. @toolchain//:bin/clang), but may be any
executable label.
""",
        ),
        "data": attr.label_list(
            allow_files = True,
            doc = """Additional files that are required for this tool to run.

Frequently, clang and gcc require additional files to execute as they often shell out to
other binaries (e.g. `cc1`).
""",
        ),
    },
    provides = [DefaultInfo],
    doc = """Declares a tool for use by toolchain actions.

`scala_tool` rules are used in a `scala_tool_map` rule to ensure all files and
metadata required to run a tool are available when constructing a `scala_toolchain`.

In general, include all files that are always required to run a tool (e.g. libexec/** and
cross-referenced tools in bin/*) in the [data](#scala_tool-data) attribute. If some files are only
required when certain flags are passed to the tool, consider using a `scala_args` rule to
bind the files to the flags that require them. This reduces the overhead required to properly
enumerate a sandbox with all the files required to run a tool, and ensures that there isn't
unintentional leakage across configurations and actions.

Example:
```
load("//toolchains/scala:tool.bzl", "scala_tool")

scala_tool(
    name = "clang_tool",
    src = "@llvm_toolchain//:bin/clang",
    # Suppose clang needs libc to run.
    data = ["@llvm_toolchain//:lib/x86_64-linux-gnu/libc.so.6"]
    tags = ["requires-network"],
    capabilities = ["//cc/toolchains/capabilities:supports_pic"],
)
```
""",
    executable = True,
)
