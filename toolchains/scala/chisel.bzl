# buildifier: disable=module-docstring
load("@rules_scala//scala:scala.bzl", "scala_binary", "scala_library", "scala_test")

def chisel_binary(name, **kwargs):
    """Wrapper for scala_binary with Chisel configuration.

    Automatically includes Chisel dependencies and compiler options.

    Args:
      name: A unique name for this target.
      **kwargs: Additional arguments to pass to scala_binary.
    """
    scala_binary(
        name = name,
        deps = [
                   "@maven//:com_chuusai_shapeless_2_13",
                   "@maven//:com_lihaoyi_os_lib_2_13",
                   "@maven//:io_circe_circe_core_2_13",
                   "@maven//:io_circe_circe_generic_2_13",
                   "@maven//:io_circe_circe_generic_extras_2_13",
                   "@maven//:io_circe_circe_parser_2_13",
                   "@maven//:org_chipsalliance_chisel_2_13",
                   "@maven//:org_typelevel_cats_core_2_13",
                   "@maven//:org_typelevel_cats_kernel_2_13",
               ] +
               kwargs.pop("deps", []),
        scalacopts = [
                         "-language:reflectiveCalls",
                         "-deprecation",
                         "-feature",
                         "-Xcheckinit",
                     ] +
                     kwargs.pop("scalacopts", []),
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_17",
        ],
        **kwargs
    )

def chisel_library(name, **kwargs):
    """Wrapper for scala_library with Chisel configuration.

    Automatically includes Chisel dependencies and compiler options.

    Args:
      name: A unique name for this target.
      **kwargs: Additional arguments to pass to scala_library.
    """
    scala_library(
        name = name,
        deps = [
                   "@maven//:com_chuusai_shapeless_2_13",
                   "@maven//:com_lihaoyi_os_lib_2_13",
                   "@maven//:io_circe_circe_core_2_13",
                   "@maven//:io_circe_circe_generic_2_13",
                   "@maven//:io_circe_circe_generic_extras_2_13",
                   "@maven//:io_circe_circe_parser_2_13",
                   "@maven//:org_chipsalliance_chisel_2_13",
                   "@maven//:org_typelevel_cats_core_2_13",
                   "@maven//:org_typelevel_cats_kernel_2_13",
               ] +
               kwargs.pop("deps", []),
        scalacopts = [
                         "-language:reflectiveCalls",
                         "-deprecation",
                         "-feature",
                         "-Xcheckinit",
                     ] +
                     kwargs.pop("scalacopts", []),
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_17",
        ],
        **kwargs
    )

def _chisel_test_wrapper_impl(ctx):
    """Implementation of chisel_test wrapper that creates a launcher script with expanded env vars."""

    # Get the underlying scala_test target
    test_target = ctx.attr.test

    # Expand location variables in environment
    expanded_env = {}
    for key, value in ctx.attr.env.items():
        expanded_env[key] = ctx.expand_location(value, ctx.attr.data)

    # Add hack for CHISEL_FIRTOOL_PATH (remove /firtool suffix from binary path)
    if "CHISEL_FIRTOOL_BINARY_PATH" in expanded_env and "CHISEL_FIRTOOL_PATH" not in expanded_env:
        expanded_env["CHISEL_FIRTOOL_PATH"] = expanded_env["CHISEL_FIRTOOL_BINARY_PATH"].replace("/firtool", "")

    # Create a launcher script that sets environment and runs the test
    launcher = ctx.actions.declare_file(ctx.label.name + "_launcher.sh")
    test_executable = test_target[DefaultInfo].files_to_run.executable

    env_exports = "\n".join([
        "export {}='{}'".format(key, value)
        for key, value in expanded_env.items()
    ])

    ctx.actions.write(
        output = launcher,
        content = """#!/bin/bash
set -e

# Navigate to runfiles directory
cd "$RUNFILES_DIR/{workspace}" || exit 1

# Expanded environment variables (convert to absolute paths)
{env_exports}

# Convert relative paths to absolute paths for use in sandbox
if [ -n "$VERILATOR_BIN" ] && [[ "$VERILATOR_BIN" != /* ]]; then
    export VERILATOR_BIN="$PWD/$VERILATOR_BIN"
fi

# Compute VERILATOR_ROOT from VERILATOR_BIN (go up two directories: bin -> root)
if [ -n "$VERILATOR_BIN" ]; then
    export VERILATOR_ROOT="$(dirname "$(dirname "$VERILATOR_BIN")")"
fi

if [ -n "$CHISEL_FIRTOOL_BINARY_PATH" ] && [[ "$CHISEL_FIRTOOL_BINARY_PATH" != /* ]]; then
    export CHISEL_FIRTOOL_BINARY_PATH="$PWD/$CHISEL_FIRTOOL_BINARY_PATH"
fi

if [ -n "$CHISEL_FIRTOOL_PATH" ] && [[ "$CHISEL_FIRTOOL_PATH" != /* ]]; then
    export CHISEL_FIRTOOL_PATH="$PWD/$CHISEL_FIRTOOL_PATH"
fi

# Add tool directories to PATH for tools that search PATH
if [ -n "$VERILATOR_BIN" ]; then
    VERILATOR_DIR="$(dirname "$VERILATOR_BIN")"
    export PATH="$VERILATOR_DIR:$PATH"
fi

if [ -n "$CHISEL_FIRTOOL_BINARY_PATH" ]; then
    FIRTOOL_DIR="$(dirname "$CHISEL_FIRTOOL_BINARY_PATH")"
    export PATH="$FIRTOOL_DIR:$PATH"
fi

# Workaround for BCR verilator: Generate verilated.mk from template
# BCR verilator 5.036.bcr.3 includes only verilated.mk.in (template), not the processed file
# Generate it at runtime to avoid modifying the BCR module
if [ -n "$VERILATOR_ROOT" ]; then
    if [[ ! -f "$VERILATOR_ROOT/include/verilated.mk" && -f "$VERILATOR_ROOT/include/verilated.mk.in" ]]; then
        sed 's/@AR@/ar/g; s/@CXX@/g++/g; s/@LINK@/g++/g; s/@OBJCACHE@//g; s/@PERL@/perl/g; s/@PYTHON3@/python3/g; s/@[A-Z_]*@//g' \\
            "$VERILATOR_ROOT/include/verilated.mk.in" > "$VERILATOR_ROOT/include/verilated.mk"
    fi

    # Workaround: Generate verilated_config.h from template if missing
    # BCR verilator 5.036.bcr.3 generates this via genrule but doesn't include it in verilator_includes
    if [[ ! -f "$VERILATOR_ROOT/include/verilated_config.h" && -f "$VERILATOR_ROOT/include/verilated_config.h.in" ]]; then
        sed 's/@PACKAGE_STRING@/Verilator 5.036/g; s/@CFG_WITH_CCWARN@/1/g; s/@CFG_WITH_LONGTESTS@/0/g; s/@[A-Z_]*@//g' \\
            "$VERILATOR_ROOT/include/verilated_config.h.in" > "$VERILATOR_ROOT/include/verilated_config.h"
    fi

    # Workaround: Symlink verilator_includer script if missing
    # BCR verilator < 5.036.bcr.4 doesn't include verilator_includer in bin/
    VERILATOR_INCLUDER=$RUNFILES_DIR/{workspace}/toolchains/verilator/verilator_includer
    if [ ! -f $VERILATOR_INCLUDER ]; then
        VERILATOR_INCLUDER="$RUNFILES_DIR/bazel-orfs+/toolchains/verilator/verilator_includer"
    fi
    if [[ ! -f "$VERILATOR_ROOT/bin/verilator_includer" ]]; then
        ln -sf "$VERILATOR_INCLUDER" "$VERILATOR_ROOT/bin/verilator_includer"
    fi
fi

# Run the actual test
exec "$RUNFILES_DIR/{workspace}/{test_path}" "$@"
""".format(
            env_exports = env_exports,
            workspace = ctx.workspace_name,
            test_path = test_executable.short_path,
        ),
        is_executable = True,
    )

    # Merge runfiles from the test target and our data deps
    runfiles = ctx.runfiles(files = [test_executable] + ctx.files.data)
    runfiles = runfiles.merge(test_target[DefaultInfo].default_runfiles)

    return [
        DefaultInfo(
            executable = launcher,
            runfiles = runfiles,
        ),
    ]

_chisel_test_with_env_test = rule(
    implementation = _chisel_test_wrapper_impl,
    attrs = {
        "data": attr.label_list(
            allow_files = True,
        ),
        "env": attr.string_dict(),
        "test": attr.label(
            mandatory = True,
            providers = [DefaultInfo],
            executable = True,
            cfg = "target",
        ),
    },
    test = True,
)

def chisel_test(name, **kwargs):
    """Wrapper for scala_test with Chisel and Verilator configuration.

    This rule creates a custom test wrapper that:
    - Automatically includes Chisel dependencies
    - Sets up Verilator and firtool environment variables
    - Runs tests locally (tags=["local"]) to allow file generation
    - Applies BCR verilator workarounds for missing config files

    Args:
      name: A unique name for this target.
      **kwargs: Additional arguments to pass to scala_test, including:
        - env: dict of additional environment variables
        - data: list of additional data dependencies
        - Other standard scala_test attributes
    """

    # Extract env dict that needs expansion
    env_to_expand = {
        # Doesn't work in hermetic mode, no point in Bazel, no home folder
        "CCACHE_DISABLE": "1",
        "CHISEL_FIRTOOL_BINARY_PATH": "$(rootpath @circt//:bin/firtool)",
        "VERILATOR_BIN": "$(rootpath @verilator//:bin/verilator)",
        # VERILATOR_ROOT will be computed dynamically in launcher script from VERILATOR_BIN
    }
    user_env = kwargs.pop("env", {})

    # Merge user env
    for key, value in user_env.items():
        if key not in env_to_expand:
            env_to_expand[key] = value

    # Common data dependencies
    data_deps = [
        "@circt//:bin/firtool",
        "@verilator//:bin/verilator",
        "@verilator//:verilator_includes",
        "@bazel-orfs//toolchains/verilator:verilator_includer",
    ] + kwargs.pop("data", [])

    # Create the underlying scala_test target
    scala_test_name = name + "_scala_inner"
    scala_test(
        name = scala_test_name,
        data = data_deps,
        deps = [
                   "@maven//:com_chuusai_shapeless_2_13",
                   "@maven//:com_lihaoyi_os_lib_2_13",
                   "@maven//:io_circe_circe_core_2_13",
                   "@maven//:io_circe_circe_generic_2_13",
                   "@maven//:io_circe_circe_generic_extras_2_13",
                   "@maven//:io_circe_circe_parser_2_13",
                   "@maven//:org_chipsalliance_chisel_2_13",
                   "@maven//:org_typelevel_cats_core_2_13",
                   "@maven//:org_typelevel_cats_kernel_2_13",
               ] +
               kwargs.pop("deps", []),
        scalacopts = [
                         "-language:reflectiveCalls",
                         "-deprecation",
                         "-feature",
                         "-Xcheckinit",
                     ] +
                     kwargs.pop("scalacopts", []),
        plugins = [
            "@maven//:org_chipsalliance_chisel_plugin_2_13_17",
        ],
        testonly = True,
        tags = ["manual"] + kwargs.pop("tags", []),
        **kwargs
    )

    # Wrap with environment expansion
    # Chisel tests run locally due to Verilator's file generation requirements
    _chisel_test_with_env_test(
        name = name,
        test = ":" + scala_test_name,
        env = env_to_expand,
        data = data_deps,
        # "local" tag runs test locally, allowing Verilator to access its include files
        # This is necessary because Verilator generates Makefiles with relative paths
        tags = ["local"] + kwargs.pop("tags", []),
    )
