load("@rules_python//python:defs.bzl", "py_binary")

# FIXME emulate python3 and get venv we need from within orfs make
py_binary(
    name = "python3",
    srcs = ["python.py"],
    main = "python.py",
    visibility = ["//visibility:public"],
    deps = [
        "@bazel-orfs-pip//pandas",
        "@bazel-orfs-pip//pyyaml",
    ],
)
