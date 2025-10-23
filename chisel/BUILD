load("//chisel:test.bzl", "chisel_bench_test")
load("//toolchains/scala:chisel.bzl", "chisel_library")

filegroup(
    name = "chiselfiles",
    srcs = glob(["**/*.scala"]),
    tags = ["manual"],
    visibility = ["//visibility:public"],
)

chisel_library(
    name = "codegenlib",
    srcs = glob(["src/main/scala/codegen/**/*.scala"]),
    tags = ["manual"],
    visibility = ["//visibility:public"],
)
