load("@rules_cc//cc:cc_test.bzl", "cc_test")
load("//chisel:test.bzl", "chisel_bench_test")
load("//toolchains/scala:chisel.bzl", "chisel_library", "chisel_test")

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

chisel_library(
    name = "applicationlib",
    srcs = glob(["src/main/scala/example/**/*.scala"]),
    tags = ["manual"],
)

chisel_bench_test(
    name = "life",
    srcs = ["src/test/scala/example/LifeUniverseTests.scala"],
    chisel_module = "example.LifeUniverseTestBench",
    module_top = "LifeUniverseTestBench",
    deps = [":applicationlib"],
)

chisel_test(
    name = "life2_test",
    srcs = ["src/test/scala/example/LifeTests.scala"],
    deps = [":applicationlib"],
)

cc_test(
    name = "life_cc_test",
    size = "small",
    srcs = ["LifeTests.cpp"],
    copts = [],
    visibility = [
    ],
    deps = [
        ":life_simulator",
        "@googletest//:gtest_main",
    ],
)
