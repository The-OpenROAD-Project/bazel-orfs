"""
This module defines rules for working with Scala libraries.
"""

load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("//toolchains/scala/impl:scala.bzl", "args_by_action")
load(
    ":scala_toolchain_info.bzl",
    "ActionTypeInfo",
    "BuiltinVariablesInfo",
    "ToolConfigInfo",
)

def _scala_library_impl(ctx):
    toolchain = ctx.toolchains["//toolchains/scala:toolchain_type"]
    compile_action = ctx.attr._compile_action[ActionTypeInfo]
    compiler = toolchain.tool_map[ToolConfigInfo].configs[compile_action]
    variable = {
        ctx.attr._variables[BuiltinVariablesInfo].variables["sources"]: depset(ctx.files.srcs),
        ctx.attr._variables[BuiltinVariablesInfo].variables["jars"]: depset([f for d in ctx.attr.deps for f in d[JavaInfo].transitive_runtime_jars.to_list()]),
        ctx.attr._variables[BuiltinVariablesInfo].variables["plugins"]: depset(ctx.files.plugins),
        ctx.attr._variables[BuiltinVariablesInfo].variables["scalacopts"]: depset(ctx.attr.scalacopts),
    }
    args = args_by_action(toolchain, variable, compile_action, ctx.label)

    ctx.actions.run(
        arguments = args.args + ["-d", ctx.outputs.jar.path],
        executable = compiler.files_to_run,
        inputs = depset(transitive = args.files),
        tools = depset([compiler.files_to_run.executable], transitive = [compiler.default_runfiles.files, compiler.default_runfiles.symlinks]),
        outputs = [ctx.outputs.jar],
        mnemonic = "Scalac",
        toolchain = "//toolchains/scala:toolchain_type",
    )

    return [
        DefaultInfo(
            files = depset([ctx.outputs.jar]),
        ),
        JavaInfo(
            output_jar = ctx.outputs.jar,
            compile_jar = None,
            deps = [dep[JavaInfo] for dep in ctx.attr.deps],
        ),
    ]

_scala_library = rule(
    implementation = _scala_library_impl,
    attrs = {
        "srcs": attr.label_list(
            allow_files = True,
        ),
        "deps": attr.label_list(
            providers = [JavaInfo],
            allow_files = True,
        ),
        "plugins": attr.label_list(
            providers = [JavaInfo],
            allow_files = True,
        ),
        "scalacopts": attr.string_list(),
        "jar": attr.output(),
        "_compile_action": attr.label(
            default = "//toolchains/scala/actions:scala_compile",
            providers = [ActionTypeInfo],
        ),
        "_variables": attr.label(
            default = "//toolchains/scala/variables:variables",
            providers = [BuiltinVariablesInfo],
        ),
    },
    provides = [
        DefaultInfo,
        JavaInfo,
    ],
    toolchains = [
        "//toolchains/scala:toolchain_type",
        "@bazel_tools//tools/jdk:toolchain_type",
    ],
)

def scala_library(name, **kwargs):
    return _scala_library(
        name = name,
        jar = name + ".jar",
        **kwargs
    )
