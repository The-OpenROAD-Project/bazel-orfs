load("@bazel_orfs_rules_python//python:defs.bzl", "py_binary")
load("//:openroad.bzl", "orfs_flow")

py_binary(
    name ="vizier",
    srcs = ["vizier.py"],
    deps = [
        "@bazel-orfs-pip//google_vizier",
        "@bazel-orfs-pip//debugpy",
        "@bazel-orfs-pip//jax",

"@bazel-orfs-pip//jaxlib",
"@bazel-orfs-pip//jaxopt",
"@bazel-orfs-pip//flax",
"@bazel-orfs-pip//optax",
"@bazel-orfs-pip//chex",
"@bazel-orfs-pip//equinox",
"@bazel-orfs-pip//jaxtyping",
"@bazel-orfs-pip//typeguard",

    ],
)

genrule(
    name = "vizier_run",
    srcs = [":autotuner.json", "previous_run.json"],
    outs = ["next_run.json"],
    cmd = "$(location :vizier) $(location :autotuner.json) $(location :previous_run.json) $@",
    tools = [":vizier"],
    visibility = ["//visibility:public"],
)
