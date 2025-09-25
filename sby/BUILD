load("//:generate.bzl", "fir_library")
load("//:sby.bzl", "sby_test")
load("//:verilog.bzl", "verilog_directory", "verilog_single_file_library", "verilog_file")
load("//toolchains/scala:chisel.bzl", "chisel_binary")

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
    resource_strip_prefix = "sby",
    resources = glob(["**/*.v"]),
    tags = ["manual"],
    deps = [
        "@maven//:com_github_scopt_scopt_2_13",
    ],
)

fir_library(
    name = "counter_fir",
    data = [
    ],
    generator = ":generate_counter",
    opts = [
        "TestCounter",
        "--disable-all-randomization",
        "-strip-debug-info",
        "-disable-layers=Verification",
        "-disable-layers=Verification.Assert",
        "-disable-layers=Verification.Assume",
        "-disable-layers=Verification.Cover",
    ],
    tags = ["manual"],
)

verilog_directory(
    name = "counter_split",
    srcs = ["counter_fir"],
    opts = [
        "--disable-all-randomization",
        "-strip-debug-info",
        "-disable-layers=Verification",
        "-disable-layers=Verification.Assert",
        "-disable-layers=Verification.Assume",
        "-disable-layers=Verification.Cover",
    ],
    tags = ["manual"],
)

verilog_single_file_library(
    name = "full.sv",
    srcs = ["counter_split"],
    tags = ["manual"],
    visibility = ["//visibility:public"],
)

# FIXME ideally we could use verilog_file directly on the fir target
# https://github.com/llvm/circt/issues/9020
#
verilog_file(
    name = "counter.sv",
    srcs = ["counter_fir"],
    opts = [
         "--disabxle-all-randomization",
         "-strip-debug-info",
            "-disable-layers=Verification",
            "-disable-layers=Verification.Assert",
            "-disable-layers=Verification.Assume",
            "-disable-layers=Verification.Cover"
    ],
    tags = ["manual"],
)

sby_test(
    name = "counter_test",
    module_top = "TestCounter",
    # FIXME runs out of disk in CI
    tags = ["manual"],
    verilog_files = [
        ":full.sv",
    ],
)
