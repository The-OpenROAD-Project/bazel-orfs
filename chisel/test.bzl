"""
This module defines Bazel rules and macros for generating, simulating, and testing Chisel hardware modules.
"""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_verilator//verilator:defs.bzl", "verilator_cc_library")
load("//:generate.bzl", "fir_library")
load("//:verilog.bzl", "verilog_directory")
load("//toolchains/scala:chisel.bzl", "chisel_binary")

def _chisel_bench_test_impl(ctx):
    test = ctx.actions.declare_file("{}_test".format(ctx.attr.name))
    ctx.actions.write(
        output = test,
        is_executable = True,
        content = """
#!/bin/sh
set -ex
{run} $TEST_UNDECLARED_OUTPUTS_DIR/{name}.vcd
""".format(
            run = ctx.executable.test_bench_runner.short_path,
            name = ctx.label.name,
        ),
    )

    return [
        DefaultInfo(
            executable = test,
            runfiles = ctx.runfiles(
                transitive_files = depset(
                    [ctx.executable.test_bench_runner],
                ),
            ),
        ),
    ]

_chisel_bench_test = rule(
    implementation = _chisel_bench_test_impl,
    attrs = {
        "test_bench_runner": attr.label(
            doc = "Runs testbench and outputs .vcd file.",
            allow_single_file = True,
            executable = True,
            cfg = "exec",
        ),
    },
    test = True,
)

def chisel_bench_test(
        name,
        srcs,
        chisel_module,
        module_top,
        deps,
        firtool_opts = [
            "--lowering-options=disallowPackedArrays,disallowLocalVariables,noAlwaysComb",
            "--disable-all-randomization",
        ],
        **kwargs):
    """Creates a Chisel benchmark test flow including code generation, FIRRTL, Verilog, simulation, and test rules.

    Args:
        name: The base name for the targets.
        srcs: List of Scala source files for the Chisel module.
        chisel_module: The Chisel module class name to generate.
        module_top: The top module name for the FIRRTL and Verilog generation.
        deps: List of dependencies for the Chisel binary.
        firtool_opts: List of options to pass to the FIRRTL tool.
        **kwargs: Additional keyword arguments.
    """
    chisel_binary(
        name = "{name}_generator".format(name = name),
        srcs = srcs,
        main_class = "codegen.CodeGen",
        tags = ["manual"],
        deps = deps + ["//chisel:codegenlib"],
    )

    fir_library(
        name = "{name}_fir".format(name = name),
        generator = ":{name}_generator".format(name = name),
        opts = [chisel_module] + firtool_opts,
        tags = ["manual"],
    )

    verilog_directory(
        name = "{name}_split".format(name = name),
        srcs = ["{name}_fir".format(name = name)],
        opts = firtool_opts,
        tags = ["manual"],
    )

    verilator_cc_library(
        name = "{name}_simulator".format(name = name),
        copts = [
            "-Os",
            "-Wno-all",
        ],
        module = "{name}_split".format(name = name),
        module_top = module_top,
        tags = ["manual"],
        trace = True,
        visibility = ["//visibility:public"],
        vopts = [],
    )
    cc_binary(
        name = "{name}_run".format(name = name),
        srcs = ["//chisel:TestBench.cpp"],
        copts = [
            # "-std=gnu++23",
            # "-g",
        ],
        local_defines = ["MODULE_TOP={module_top}".format(module_top = module_top)],
        linkopts = ["-latomic"],
        tags = ["manual"],
        visibility = ["//visibility:public"],
        deps = [
            ":{name}_simulator".format(name = name),
        ],
    )

    _chisel_bench_test(
        name = "{name}_test".format(name = name),
        test_bench_runner = ":{name}_run".format(name = name),
        **kwargs
    )
