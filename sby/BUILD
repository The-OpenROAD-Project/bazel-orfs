load("@rules_chisel//chisel:defs.bzl", "chisel_binary")
load("//:sby.bzl", "sby_test")

filegroup(
    name = "chiselfiles",
    srcs = glob(["**/*.scala"]),
    tags = ["manual"],
    visibility = ["//visibility:public"],
)

chisel_binary(
    name = "generate_counter",
    srcs = glob(["**/*.scala"]),
    main_class = "CodeGen",
    tags = ["manual"],
    deps = [
        "@maven//:com_github_scopt_scopt_2_13",
    ],
)

sby_test(
    name = "counter",
    generator = ":generate_counter",
    generator_opts = ["TestCounter"],
    module_top = "TestCounter",
    verilog_files = [":FormalCounter.v"],
)
