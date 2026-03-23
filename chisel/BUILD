load("@rules_cc//cc:cc_test.bzl", "cc_test")
load("@rules_chisel//chisel:defs.bzl", "chisel_binary", "chisel_library", "chisel_test")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("@bazel-orfs-verilog//:generate.bzl", "fir_library")
load("//:openroad.bzl", "orfs_synth")
load("@bazel-orfs-verilog//:verilog.bzl", "verilog_directory", "verilog_single_file_library")
load("//chisel:test.bzl", "chisel_bench_test")

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

# =============================================================================
# HelloWorld: Chisel -> FIRRTL -> Verilog -> ORFS synthesis
# =============================================================================

HELLOWORLD_FIRTOOL_OPTS = [
    "--lowering-options=disallowPackedArrays,disallowLocalVariables,noAlwaysComb",
    "--disable-all-randomization",
]

chisel_binary(
    name = "helloworld_generator",
    srcs = [],
    main_class = "codegen.CodeGen",
    tags = ["manual"],
    deps = [
        ":applicationlib",
        ":codegenlib",
    ],
)

fir_library(
    name = "helloworld_fir",
    generator = ":helloworld_generator",
    opts = ["example.HelloWorld"] + HELLOWORLD_FIRTOOL_OPTS,
    tags = ["manual"],
)

verilog_directory(
    name = "helloworld_split",
    srcs = [":helloworld_fir"],
    opts = HELLOWORLD_FIRTOOL_OPTS,
    tags = ["manual"],
)

verilog_single_file_library(
    name = "helloworld.sv",
    srcs = [":helloworld_split"],
    tags = ["manual"],
)

orfs_synth(
    name = "HelloWorld_synth",
    arguments = {
        "SDC_FILE": "$(location :constraints-helloworld.sdc)",
    },
    data = [":constraints-helloworld.sdc"],
    module_top = "HelloWorld",
    tags = ["manual"],
    verilog_files = [":helloworld.sv"],
)

filegroup(
    name = "HelloWorld_synth_odb",
    srcs = [":HelloWorld_synth"],
    output_group = "1_synth.odb",
    tags = ["manual"],
)

sh_test(
    name = "helloworld_synth_test",
    srcs = ["helloworld_synth_test.sh"],
    args = ["$(locations :HelloWorld_synth_odb)"],
    data = [":HelloWorld_synth_odb"],
    tags = ["manual"],
)

# =============================================================================
# HelloWorld synthesis from verilog_directory (TreeArtifact) directly,
# without the verilog_single_file_library concatenation workaround.
# Tests EXPAND_VERILOG_DIRS shell expansion of directory entries.
# =============================================================================

orfs_synth(
    name = "HelloWorld_dir_synth",
    arguments = {
        "SDC_FILE": "$(location :constraints-helloworld.sdc)",
    },
    data = [":constraints-helloworld.sdc"],
    module_top = "HelloWorld",
    tags = ["manual"],
    verilog_files = [":helloworld_split"],
)

filegroup(
    name = "HelloWorld_dir_synth_odb",
    srcs = [":HelloWorld_dir_synth"],
    output_group = "1_synth.odb",
    tags = ["manual"],
)

sh_test(
    name = "helloworld_dir_synth_test",
    srcs = ["helloworld_synth_test.sh"],
    args = ["$(locations :HelloWorld_dir_synth_odb)"],
    data = [":HelloWorld_dir_synth_odb"],
    tags = ["manual"],
)
