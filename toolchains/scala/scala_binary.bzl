"""
Fiddly bits missing from rules_scala that we implement ourselves.
"""

load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("//toolchains/scala/impl:scala.bzl", "args_by_action")
load(
    ":scala_toolchain_info.bzl",
    "ActionTypeInfo",
    "BuiltinVariablesInfo",
    "ToolConfigInfo",
)

SCALA_EXECUTABLE_ATTRS = {
    "srcs": attr.label_list(
        allow_files = True,
    ),
    "data": attr.label_list(
        providers = [DefaultInfo],
        allow_files = True,
    ),
    "deps": attr.label_list(
        providers = [JavaInfo],
        allow_files = True,
    ),
    "main_class": attr.string(
        mandatory = True,
    ),
    "plugins": attr.label_list(
        providers = [JavaInfo],
        allow_files = True,
    ),
    "scalacopts": attr.string_list(
        default = [],
    ),
    "jar": attr.output(),
    "stripped_jar": attr.output(mandatory = False),
    "_compile_action": attr.label(
        default = "//toolchains/scala/actions:scala_compile",
        providers = [ActionTypeInfo],
    ),
    "_variables": attr.label(
        default = "//toolchains/scala/variables:variables",
        providers = [BuiltinVariablesInfo],
    ),
    "resources": attr.label_list(
        allow_files = True,
        mandatory = False,
        doc = "Resource files or directories to include in the JAR",
    ),
    "resource_strip_prefix": attr.string(
        default = "",
        doc = "If non-empty, strip this prefix from the paths of resources",
    ),
}

def relpath(dst, src):
    return "/".join([".." for _ in src.dirname.split("/")] + [dst.path])

def toolchain_binary(java_toolchain, basename):
    bins = [file for file in java_toolchain.java.java_runtime.files.to_list() if file.basename == basename]
    if len(bins) != 1:
        fail("expected a single java binary")
    return bins[0]

def java_binary(java_toolchain):
    _, _, basename = java_toolchain.java.java_runtime.java_executable_exec_path.rpartition("/")
    return toolchain_binary(java_toolchain, basename)

def jar_binary(java_toolchain):
    return toolchain_binary(java_toolchain, "jar")

def _merge_impls(*impls):
    return lambda ctx: [p for impl in impls for p in impl(ctx)]

def _env_impl(ctx):
    return [
        RunEnvironmentInfo(
            environment = {k: ctx.expand_location(v) for k, v in ctx.attr.env.items()},
        ),
    ]

def _scala_binary_impl(ctx):
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

    jars = []
    if ctx.files.srcs:
        stripped = ctx.outputs.stripped_jar if ctx.attr.stripped_jar else ctx.actions.declare_file(ctx.label.name + ".stripped.jar")
        ctx.actions.run(
            arguments = args.args + ["-d", stripped.path],
            executable = compiler.files_to_run,
            inputs = depset(transitive = args.files),
            tools = depset([compiler.files_to_run.executable], transitive = [compiler.default_runfiles.files, compiler.default_runfiles.symlinks]),
            outputs = [stripped],
            mnemonic = "Scalac",
            toolchain = "//toolchains/scala:toolchain_type",
        )
        jars.append(stripped)

    classpath = depset(
        jars,
        transitive = [toolchain.runfiles.files] +
                     [dep[JavaInfo].transitive_runtime_jars for dep in ctx.attr.deps],
    )
    manifest = ctx.actions.declare_file(ctx.label.name + ".Manifest.txt")

    resources_path = "generate_counter_java.runfiles/_main/sby"  # _dirname(relpath(ctx.files.resources[0], ctx.outputs.jar)) if ctx.files.resources else None

    content = ("Main-Class: " + ctx.attr.main_class +
               "\nClass-Path:" +
               "\n".join(["  " + relpath(f, ctx.outputs.jar) for f in (classpath.to_list())] +
                         ["  " + resources_path] if ctx.files.resources else []) +
               "\n")
    ctx.actions.write(
        output = manifest,
        content = content,
    )

    jar = jar_binary(ctx.toolchains["@bazel_tools//tools/jdk:toolchain_type"])
    jar_args = ctx.actions.args()
    jar_args.add("--create")
    jar_args.add("--manifest", manifest)
    jar_args.add("--file", ctx.outputs.jar)

    resources = ctx.files.resources
    if resources:
        for resource in resources:
            jar_args.add("-C", resource.dirname)
            jar_args.add(resource.basename)

    ctx.actions.run(
        executable = jar,
        arguments = [jar_args],
        inputs = depset([manifest] + jars + resources),
        tools = depset([jar]),
        outputs = [ctx.outputs.jar],
        mnemonic = "Jar",
        toolchain = "//toolchains/scala:toolchain_type",
    )

    link = ctx.actions.declare_file(ctx.label.name + "_java")
    ctx.actions.symlink(
        output = link,
        # TODO: Move java stuff into scala toolchain
        target_file = java_binary(ctx.toolchains["@bazel_tools//tools/jdk:toolchain_type"]),
        is_executable = True,
    )

    # FIXME is there a better way to check if this is a test?
    is_test = ctx.label.name.endswith("_test")

    if is_test:
        wrapper = ctx.actions.declare_file(ctx.label.name)
        script = """#!/bin/bash
set -ex
if [[ -n "$TESTBRIDGE_TEST_ONLY" ]]; then
exec {java_bin} "$@" -z "$TESTBRIDGE_TEST_ONLY"
else
exec {java_bin} "$@"
fi
""".format(java_bin = link.short_path)
        ctx.actions.write(output = wrapper, content = script, is_executable = True)
    else:
        wrapper = link

    return [DefaultInfo(
        files = depset([ctx.outputs.jar] + ([ctx.outputs.stripped_jar] if ctx.attr.stripped_jar else [])),
        runfiles = ctx.runfiles(
            [wrapper, ctx.outputs.jar] + ([link] if is_test else []),
            transitive_files = depset(transitive = [classpath, depset(ctx.files.data), depset(ctx.files.resources)]),
        ),
        executable = wrapper,
    )]

_scala_binary = rule(
    implementation = _scala_binary_impl,
    attrs = SCALA_EXECUTABLE_ATTRS,
    executable = True,
    provides = [
        DefaultInfo,
    ],
    toolchains = [
        "//toolchains/scala:toolchain_type",
        "@bazel_tools//tools/jdk:toolchain_type",
    ],
)

def scala_binary(name, **kwargs):
    jar = name + ".jar"
    return _scala_binary(
        name = name,
        jar = jar,
        args = [
            "-jar",
            "$(location {})".format(jar),
        ],
        **kwargs
    )

_scala_test = rule(
    implementation = _merge_impls(_scala_binary_impl, _env_impl),
    attrs = SCALA_EXECUTABLE_ATTRS | {
        "env": attr.string_dict(),
    },
    executable = True,
    test = True,
    provides = [
        DefaultInfo,
        RunEnvironmentInfo,
    ],
    toolchains = [
        "//toolchains/scala:toolchain_type",
        "@bazel_tools//tools/jdk:toolchain_type",
    ],
)

def scala_test(name, **kwargs):
    jar = name + ".jar"
    stripped_jar = name + "_stripped.jar"
    return _scala_test(
        name = name,
        jar = jar,
        stripped_jar = stripped_jar,
        args = [
            "-jar",
            "$(location {})".format(jar),
            "-R",
            "$(location :{})".format(stripped_jar),
            "-e",
        ] + kwargs.pop("args", []),
        main_class = kwargs.pop("main_class", "org.scalatest.tools.Runner"),
        deps = kwargs.pop("deps", []) + [
            "@maven//:org_scalatest_scalatest_2_13",
        ],
        **kwargs
    )
