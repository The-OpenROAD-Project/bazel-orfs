# Unused in CI
#
# load("@bazel-orfs//tools/pin:pin.bzl", "pin_data")
load("@rules_python//python:defs.bzl", "py_binary", "py_library", "py_test")
load("@rules_python//python:pip.bzl", "compile_pip_requirements")
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

# OpenROAD and OpenSTA binaries from the latest ORFS Docker image.
# Downstream projects use these labels to skip building OpenROAD from source:
#   orfs.default(
#       openroad = "@bazel-orfs//:openroad-latest",
#       opensta = "@bazel-orfs//:opensta-latest",
#   )
# The Docker image is only downloaded when these targets are actually built.
alias(
    name = "openroad-latest",
    actual = "@docker_orfs_image//:openroad",
    visibility = ["//visibility:public"],
)

alias(
    name = "opensta-latest",
    actual = "@docker_orfs_image//:sta",
    visibility = ["//visibility:public"],
)

exports_files([
    "bump.py",
    "config_mk_parser.py",
    "deploy.tpl",
    "eqy.tpl",
    "eqy-write-verilog.tcl",
    "make.tpl",
    "oci_extract.py",
    "package_stage.py",
    "mock_area.tcl",
    "openroad-unsetenv-runfiles.patch",
    "oss_cad_suite.BUILD.bazel",
    "parallel_synth.mk",
    "rtlil_kept_modules.py",
    "sby.tpl",
    "synth.tcl",
    "synth_keep.tcl",
    "synth_partition.sh",
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

# From any project using bazel-orfs run `bazelisk run @bazel-orfs//:bump`
# to upgrade ORFS and bazel-orfs.
py_binary(
    name = "bump",
    srcs = ["bump.py"],
    data = ["oci_extract.py"],
    main = "bump.py",
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

py_test(
    name = "patcher_test",
    srcs = [
        "patcher.py",
        "patcher_test.py",
    ],
    main = "patcher_test.py",
)

# Run `bazelisk run //:monitor-test` to run tests with stage monitoring.
# Usage: bazelisk run //:monitor-test -- //test/...
py_binary(
    name = "monitor-test",
    srcs = ["monitor_test.py"],
    main = "monitor_test.py",
)

py_test(
    name = "monitor-test-test",
    srcs = ["monitor_test_test.py"],
    main = "monitor_test_test.py",
    deps = [":monitor-test"],
)

# Run `bazelisk run //:deps -- //pkg:target` to deploy stage inputs
# for interactive debugging. Only builds the deps output group (cheap).
sh_binary(
    name = "deps",
    srcs = ["deps_wrapper.sh"],
    visibility = ["//visibility:public"],
)

py_library(
    name = "config_mk_parser_lib",
    srcs = ["config_mk_parser.py"],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "config_mk_parser",
    srcs = ["config_mk_parser.py"],
    visibility = ["//visibility:public"],
)

py_test(
    name = "config_mk_parser_test",
    srcs = ["config_mk_parser_test.py"],
    deps = [":config_mk_parser_lib"],
)

py_library(
    name = "rtlil_kept_modules_lib",
    srcs = ["rtlil_kept_modules.py"],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "rtlil_kept_modules",
    srcs = ["rtlil_kept_modules.py"],
    visibility = ["//visibility:public"],
)

py_test(
    name = "rtlil_kept_modules_test",
    srcs = ["rtlil_kept_modules_test.py"],
    deps = [":rtlil_kept_modules_lib"],
)

# Run `bazelisk run //:fix_lint` to format all files changed since origin/main.
py_library(
    name = "fix_lint_lib",
    srcs = ["fix_lint.py"],
    visibility = ["//test:__pkg__"],
)

py_binary(
    name = "fix_lint",
    srcs = ["fix_lint.py"],
    data = ["@buildifier_prebuilt//:buildifier"],
    main = "fix_lint.py",
    visibility = ["//visibility:public"],
)
