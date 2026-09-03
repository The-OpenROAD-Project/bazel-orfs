load("@bazel-orfs-eta-pip//:requirements.bzl", "requirement")
load("@rules_python//python:defs.bzl", "py_binary", "py_library")
load("@rules_python//python:pip.bzl", "compile_pip_requirements")

# Study machinery for ideas/eta.md. Committed so the numbers in that
# document can be reproduced or disputed; deleted in one commit if the
# idea does not survive its own evidence.

package(default_visibility = ["//visibility:private"])

py_library(
    name = "eta_lib",
    srcs = [
        "forecast.py",
        "parse.py",
    ],
)

py_binary(
    name = "collect",
    srcs = ["collect.py"],
    deps = [":eta_lib"],
)

py_binary(
    name = "backtest",
    srcs = ["backtest.py"],
    deps = [":eta_lib"],
)

py_library(
    name = "backtest_lib",
    srcs = ["backtest.py"],
    deps = [":eta_lib"],
)

py_binary(
    name = "plots",
    srcs = ["plots.py"],
    deps = [":backtest_lib"],
)

# The TimesFM leg. Separate binary and separate pip hub so the torch
# dependency touches nothing else in the repo, and so a machine without
# it can still run everything above.
py_binary(
    name = "timesfm_eval",
    srcs = ["timesfm_eval.py"],
    deps = [
        ":backtest_lib",
        requirement("timesfm"),
        requirement("torch"),
    ],
)

compile_pip_requirements(
    name = "requirements_eta",
    src = "requirements_eta.in",
    python_version = "3.13",
    requirements_txt = "requirements_eta_lock_3_13.txt",
)
