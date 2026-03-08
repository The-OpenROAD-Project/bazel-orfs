# Unused in CI
#
# load("@bazel-orfs//tools/pin:pin.bzl", "pin_data")
load("@rules_python//python:defs.bzl", "py_binary")
load("@rules_python//python:pip.bzl", "compile_pip_requirements")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

exports_files([
    "deploy.tpl",
    "eqy.tpl",
    "eqy-write-verilog.tcl",
    "make.tpl",
    "mock_area.tcl",
    "open_plots.sh",
    "oss_cad_suite.BUILD.bazel",
    "power.tcl",
    "sby.tpl",
])

compile_pip_requirements(
    name = "requirements",
    src = "requirements.in",
    python_version = "3.13",
    requirements_txt = "requirements_lock_3_13.txt",
)

py_binary(
    name = "plot_repair",
    srcs = [
        "plot-retiming.py",
    ],
    main = "plot-retiming.py",
    visibility = ["//visibility:public"],
    deps = ["@bazel-orfs-pip//matplotlib"],
)

py_binary(
    name = "plot_clock_period_tool",
    srcs = [
        "plot_clock_period.py",
    ],
    main = "plot_clock_period.py",
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-pip//matplotlib",
        "@bazel-orfs-pip//pyyaml",
    ],
)

# From any project using bazel-orfs run `bazelisk run @bazel-orfs//:bump`
# to upgrade ORFS and bazel-orfs.
sh_binary(
    name = "bump",
    srcs = ["bump.sh"],
    visibility = ["//visibility:public"],
)

