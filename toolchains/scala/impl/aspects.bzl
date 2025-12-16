"""
This module defines aspects for working with Scala code.
"""

load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load(
    "//toolchains/scala:scala_toolchain_info.bzl",
    "ActionTypeInfo",
    "BuiltinVariablesInfo",
    "ToolConfigInfo",
)
load("//toolchains/scala/impl:scala.bzl", "args_by_action")

SemanticDbInfo = provider(
    "Holds `compile_commands.json` databases.",
    fields = {
        "compiler": "Scala compiler.",
        "deps": "Sequence of dependencies.",
        "jars": "Sequence of jars.",
        "scalacopts": "Scala compiler options.",
        "srcs": "Sequence of sources.",
    },
)

_scala_rules = [
    "_scala_binary",
    "_scala_library",
]

def _scala_diagnostics_aspect_impl(_target, ctx):
    toolchain = ctx.toolchains["//toolchains/scala:toolchain_type"]
    action = ctx.attr._compile_action[ActionTypeInfo]
    compiler = toolchain.tool_map[ToolConfigInfo].configs[action]

    if ctx.rule.kind not in _scala_rules:
        return [
            SemanticDbInfo(
                compiler = compiler,
                scalacopts = depset([]),
                jars = depset([]),
                deps = depset([]),
                srcs = depset([]),
            ),
        ]

    variable = {
        ctx.rule.attr._variables[BuiltinVariablesInfo].variables["sources"]: depset(
            ctx.rule.files.srcs,
        ),
        ctx.rule.attr._variables[BuiltinVariablesInfo].variables["jars"]: depset(
            [
                f
                for d in ctx.rule.attr.deps
                for f in d[JavaInfo].transitive_runtime_jars.to_list()
            ],
        ),
        ctx.rule.attr._variables[BuiltinVariablesInfo].variables["plugins"]: depset(
            ctx.rule.files.plugins,
        ),
        ctx.rule.attr._variables[BuiltinVariablesInfo].variables["scalacopts"]: depset(
            ctx.rule.attr.scalacopts,
        ),
    }

    # TODO: Pass `scalacopts` from toolchain
    args_by_action(toolchain, variable, action, ctx.label)

    return [
        SemanticDbInfo(
            compiler = compiler,
            scalacopts = depset(ctx.rule.attr.scalacopts),
            jars = depset(
                [
                    f
                    for d in ctx.rule.attr.deps
                    for f in d[JavaInfo].transitive_runtime_jars.to_list()
                ],
            ),
            deps = depset(ctx.rule.attr.deps),
            srcs = depset(ctx.rule.files.srcs),
        ),
    ]

scala_diagnostics_aspect = aspect(
    attr_aspects = ["deps"],
    attrs = {
        "_compile_action": attr.label(
            default = "//toolchains/scala/actions:scala_compile",
            providers = [ActionTypeInfo],
        ),
    },
    provides = [],
    implementation = _scala_diagnostics_aspect_impl,
    apply_to_generating_rules = True,
    toolchains = [
        "//toolchains/scala:toolchain_type",
    ],
)
