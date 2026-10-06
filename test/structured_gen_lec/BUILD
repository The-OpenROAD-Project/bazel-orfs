# structured_gen's register files against yosys's synthesis of the RTL
# they replace, by logic equivalence (kepler-formal, //test/lec). The RTL
# comes from lec_fixture.py, which at XiangShan's sizes reproduces
# firtool's FpRegFile, VfRegFile and IntRegFile token for token
# (faithful_test); here it is small, so a check takes seconds: the
# generator builds every size from the same code. Every test is manual.
#
#   bazelisk test //test/structured_gen_lec:all_lec_tests

load("@rules_python//python:defs.bzl", "py_binary", "py_library", "py_test")
load(":regfile_lec.bzl", "regfile_lec")

py_binary(
    name = "lec_fixture",
    srcs = ["lec_fixture.py"],
    main = "lec_fixture.py",
)

py_library(
    name = "lec_fixture_lib",
    srcs = [
        "lec_fixture.py",
        "tokdiff.py",
    ],
)

# kepler-formal reads liberty uncompressed.
[genrule(
    name = "asap7_" + kind,
    srcs = ["@orfs//flow:platforms/asap7/lib/NLDM/asap7sc7p5t_%s_RVT_FF_nldm_%s.lib.gz" % (
        kind.upper(),
        date,
    )],
    outs = ["asap7_%s.lib" % kind],
    cmd = "gunzip -c $< > $@",
) for kind, date in [
    ("ao", "211120"),
    ("simple", "211120"),
    ("invbuf", "220122"),
]]

# The shapes, each at a few small sizes. Int starts at 16 words: at 8 a
# bank's address is one bit, and yosys names a one-bit register without
# the [0] the spec's name pattern carries.
SHAPES = {
    # RobEntryFile, RenameBufferFile, the Ftq queues: a combinational read.
    "comb": (
        "--reads 4 --writes 2 --latency 0",
        [
            8,
            16,
            32,
        ],
    ),
    # FpRegFile: the read address registered.
    "fp": (
        "--reads 14 --writes 7 --latency 1 --gen-banks 2",
        [
            8,
            16,
            32,
        ],
    ),
    # VfRegFile.
    "vf": (
        "--reads 14 --writes 7 --latency 1 --gen-banks 2",
        [
            8,
            16,
            32,
        ],
    ),
    # IntRegFile: banked reads over interleaved banks, word 0 the zero.
    "int": (
        "--reads 12 --writes 9 --latency 1 --banks 4 --banked --zero-word",
        [
            16,
            32,
        ],
    ),
}

[regfile_lec(
    name = "%s%d_lec_test" % (shape, words),
    args = "--words %d --bits 4 %s" % (words, args),
    module = "%s%d" % (
        shape.capitalize(),
        words,
    ),
) for shape, (args, sizes) in SHAPES.items() for words in sizes]

# The bug this harness was written for: the generator read a registered
# address combinationally. A spec that says so (read_latency 0) for an
# RTL that registers it must be caught.
regfile_lec(
    name = "fp8_unregistered_lec_test",
    args = "--words 8 --bits 4 --reads 14 --writes 7 --latency 1",
    expect_equivalent = False,
    module = "Fp8u",
    spec_args = "--spec-latency 0",
)

test_suite(
    name = "all_lec_tests",
    tags = ["manual"],
    tests = ["%s%d_lec_test" % (shape, words) for shape, (_, sizes) in SHAPES.items() for words in sizes] + [
        "fp8_unregistered_lec_test",
    ],
)

# The fixture is firtool's own text at XiangShan's sizes: each module of
# the generated XiangShan Verilog against lec_fixture.py, token for token.
# Manual: it needs the Chisel build of XiangShan.
py_test(
    name = "faithful_test",
    size = "small",
    srcs = ["faithful_test.py"],
    args = ["$(rootpath //test/coremark_joule/xiangshan:xiangshan_flat.sv)"],
    data = ["//test/coremark_joule/xiangshan:xiangshan_flat.sv"],
    main = "faithful_test.py",
    tags = ["manual"],
    deps = [":lec_fixture_lib"],
)
