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
    "data": attr.label_list(
        providers = [DefaultInfo],
        allow_files = True,
    ),
    "deps": attr.label_list(
        providers = [JavaInfo],
        allow_files = True,
    ),
    "jar": attr.output(),
    "main_class": attr.string(
        mandatory = True,
    ),
    "plugins": attr.label_list(
        providers = [JavaInfo],
        allow_files = True,
    ),
    "resource_strip_prefix": attr.string(
        default = "",
        doc = "If non-empty, strip this prefix from the paths of resources",
    ),
    "resources": attr.label_list(
        allow_files = True,
        mandatory = False,
        doc = "Resource files or directories to include in the JAR",
    ),
    "scalacopts": attr.string_list(
        default = [],
    ),
    "srcs": attr.label_list(
        allow_files = True,
    ),
    "stripped_jar": attr.output(mandatory = False),
    "_compile_action": attr.label(
        default = "//toolchains/scala/actions:scala_compile",
        providers = [ActionTypeInfo],
    ),
    "_variables": attr.label(
        default = "//toolchains/scala/variables:variables",
        providers = [BuiltinVariablesInfo],
    ),
}

def relpath(dst, src):
    return "/".join([".." for _ in src.dirname.split("/")] + [dst.path])

def toolchain_binary(java_toolchain, basename):
    bins = [
        file
        for file in java_toolchain.java.java_runtime.files.to_list()
        if file.basename == basename
    ]
    if len(bins) != 1:
        fail("expected a single java binary")
    return bins[0]

def java_binary(java_toolchain):
    _, _, basename = (
        java_toolchain.java.java_runtime.java_executable_exec_path.rpartition("/")
    )
    return toolchain_binary(java_toolchain, basename)

def jar_binary(java_toolchain):
    return toolchain_binary(java_toolchain, "jar")

def _merge_impls(*impls):
    return lambda ctx: [p for impl in impls for p in impl(ctx)]

def _env_impl(ctx):
    expanded = {k: ctx.expand_location(v, ctx.attr.data) for k, v in ctx.attr.env.items()}
    if "CHISEL_FIRTOOL_BINARY_PATH" in expanded and "CHISEL_FIRTOOL_PATH" not in expanded:
        # Hack to remove the /firtool suffix added by rootpath expansion to get the folder
        expanded["CHISEL_FIRTOOL_PATH"] = expanded["CHISEL_FIRTOOL_BINARY_PATH"].replace("/firtool", "")

    return [
        RunEnvironmentInfo(
            environment = expanded,
        ),
    ]

def _scala_binary_impl(ctx):
    toolchain = ctx.toolchains["//toolchains/scala:toolchain_type"]
    compile_action = ctx.attr._compile_action[ActionTypeInfo]
    compiler = toolchain.tool_map[ToolConfigInfo].configs[compile_action]
    variable = {
        ctx.attr._variables[BuiltinVariablesInfo].variables["sources"]: depset(
            ctx.files.srcs,
        ),
        ctx.attr._variables[BuiltinVariablesInfo].variables["jars"]: depset(
            [
                f
                for d in ctx.attr.deps
                for f in d[JavaInfo].transitive_runtime_jars.to_list()
            ],
        ),
        ctx.attr._variables[BuiltinVariablesInfo].variables["plugins"]: depset(
            ctx.files.plugins,
        ),
        ctx.attr._variables[BuiltinVariablesInfo].variables["scalacopts"]: depset(
            ctx.attr.scalacopts,
        ),
    }
    args = args_by_action(toolchain, variable, compile_action, ctx.label)

    jars = []
    if ctx.files.srcs:
        stripped = (
            ctx.outputs.stripped_jar if ctx.attr.stripped_jar else ctx.actions.declare_file(ctx.label.name + ".stripped.jar")
        )
        ctx.actions.run(
            arguments = args.args + ["-d", stripped.path],
            executable = compiler.files_to_run,
            inputs = depset(transitive = args.files),
            tools = depset(
                [compiler.files_to_run.executable],
                transitive = [
                    compiler.default_runfiles.files,
                    compiler.default_runfiles.symlinks,
                ],
            ),
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

    content = (
        "Main-Class: " +
        ctx.attr.main_class +
        "\nClass-Path:" +
        "\n".join(["  " + relpath(f, ctx.outputs.jar) for f in (classpath.to_list())]) +
        "\n"
    )
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
        target_file = java_binary(
            ctx.toolchains["@bazel_tools//tools/jdk:toolchain_type"],
        ),
        is_executable = True,
    )

    # FIXME is there a better way to check if this is a test?
    is_test = ctx.label.name.endswith("_test")

    if is_test:
        wrapper = ctx.actions.declare_file(ctx.label.name)
        script = """#!/bin/bash
set -ex
# HACK! _main/.. is where we find external dependencies
RUNFILES_DIR=$(cd $PWD/.. && pwd)
# verilator+ is at runfiles/verilator+
export VERILATOR_ROOT="$RUNFILES_DIR/verilator+"
# Workaround for BCR verilator 5.036.bcr.3: Generate verilated_config.h from template
# if future version includes pre-configured verilated_config.h, so this workaround won't run
if [[ ! -f "$VERILATOR_ROOT/include/verilated_config.h" && -f "$VERILATOR_ROOT/include/verilated_config.h.in" ]]; then
  sed 's/@PACKAGE_NAME@/Verilator/g; s/@PACKAGE_VERSION@/5.036/g; s/@VERILATOR_VERSION_INTEGER@/530000/g' \\
    "$VERILATOR_ROOT/include/verilated_config.h.in" > "$VERILATOR_ROOT/include/verilated_config.h"
fi
# Workaround for BCR verilator 5.036.bcr.3: Generate verilated.mk from template
# if future version includes pre-configured verilated.mk, so this workaround won't run
if [[ ! -f "$VERILATOR_ROOT/include/verilated.mk" && -f "$VERILATOR_ROOT/include/verilated.mk.in" ]]; then
  sed 's/@AR@/ar/g; s/@CXX@/g++/g; s/@LINK@/g++/g; s/@OBJCACHE@//g; s/@PERL@/perl/g; s/@PYTHON3@/python3/g; s/@[A-Z_]*@//g' \\
    "$VERILATOR_ROOT/include/verilated.mk.in" > "$VERILATOR_ROOT/include/verilated.mk"
fi
# Workaround for BCR verilator 5.036.bcr.3: Symlink our verilator_includer script
# if future version includes verilator_includer in bin/, so this workaround won't run
VERILATOR_INCLUDER=$PWD/toolchains/verilator/verilator_includer
if [ ! -f $VERILATOR_INCLUDER ]; then
  VERILATOR_INCLUDER="$RUNFILES_DIR/bazel-orfs+/toolchains/verilator/verilator_includer"
fi
if [[ ! -f "$VERILATOR_ROOT/bin/verilator_includer" ]]; then
  ln -sf "$VERILATOR_INCLUDER" "$VERILATOR_ROOT/bin/verilator_includer"
fi
# Set VERILATOR_BIN to relative path that chisel expects (bin/verilator)
export VERILATOR_BIN="bin/verilator"
# Add verilator bin directory to PATH so chisel can find verilator executable
export PATH="$VERILATOR_ROOT/bin:$PATH"
if [[ -n "$TESTBRIDGE_TEST_ONLY" ]]; then
exec {java_bin} "$@" -z "$TESTBRIDGE_TEST_ONLY"
else
exec {java_bin} "$@"
fi
""".format(
            java_bin = link.short_path,
        )
        ctx.actions.write(output = wrapper, content = script, is_executable = True)
    else:
        wrapper = link

    return [
        DefaultInfo(
            files = depset(
                [ctx.outputs.jar] +
                ([ctx.outputs.stripped_jar] if ctx.attr.stripped_jar else []),
            ),
            runfiles = ctx.runfiles(
                [wrapper, ctx.outputs.jar] + ([link] if is_test else []),
                transitive_files = depset(
                    transitive = [
                        classpath,
                        depset(ctx.files.data),
                        depset(ctx.files.resources),
                    ],
                ),
            ),
            executable = wrapper,
        ),
    ]

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
    attrs = SCALA_EXECUTABLE_ATTRS |
            {
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
               ] +
               kwargs.pop("args", []),
        main_class = kwargs.pop("main_class", "org.scalatest.tools.Runner"),
        deps = kwargs.pop("deps", []) +
               [
                   "@maven//:org_scalatest_scalatest_2_13",
               ],
        **kwargs
    )
