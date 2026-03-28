load("@rules_python//python:defs.bzl", "py_binary")
load("@rules_shell//shell:sh_test.bzl", "sh_test")

# FIXME emulate python3 and get venv we need from within orfs make
py_binary(
    name = "python3",
    srcs = ["python.py"],
    main = "python.py",
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-pip//pyyaml",
    ],
)

sh_test(
    name = "python3_test",
    srcs = ["python3_test.sh"],
    args = ["$(rootpath :python3)"],
    data = [":python3"],
)
