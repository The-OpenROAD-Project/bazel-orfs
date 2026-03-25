# Unused in CI
#
# load("@bazel-orfs//tools/pin:pin.bzl", "pin_data")
load("@rules_python//python:defs.bzl", "py_binary", "py_test")
load("@rules_python//python:pip.bzl", "compile_pip_requirements")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

exports_files([
    "bump.sh",
    "deploy.tpl",
    "eqy.tpl",
    "oci_extract.py",
    "eqy-write-verilog.tcl",
    "make.tpl",
    "mock_area.tcl",
    "open_plots.sh",
    "openroad-llvm-root-only.patch",
    "openroad-visibility.patch",
    "oss_cad_suite.BUILD.bazel",
    "power.tcl",
    "sby.tpl",
])

sh_binary(
    name = "klayout",
    srcs = ["klayout.sh"],
    visibility = ["//visibility:public"],
)

sh_binary(
    name = "openroad",
    srcs = ["openroad_wrapper.sh"],
    visibility = ["//visibility:public"],
)

compile_pip_requirements(
    name = "requirements",
    src = "requirements.in",
    python_version = "3.13",
    requirements_txt = "requirements_lock_3_13.txt",
)

compile_pip_requirements(
    name = "requirements_features",
    src = "requirements_features.in",
    python_version = "3.13",
    requirements_txt = "requirements_features_lock_3_13.txt",
)

py_binary(
    name = "plot_clock_period_tool",
    srcs = [
        "plot_clock_period.py",
    ],
    main = "plot_clock_period.py",
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-features-pip//matplotlib",
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

py_test(
    name = "oci_extract_test",
    srcs = [
        "oci_extract.py",
        "oci_extract_test.py",
    ],
    main = "oci_extract_test.py",
)

# Run `bazelisk run //:fix_lint` to format all files changed since origin/main.
sh_binary(
    name = "fix_lint",
    srcs = ["fix_lint.sh"],
    data = ["@buildifier_prebuilt//:buildifier"],
    visibility = ["//visibility:public"],
)
