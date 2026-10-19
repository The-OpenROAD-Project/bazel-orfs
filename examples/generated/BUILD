# RTL from a generator: Bazel runs gen_mac.py, and the flow reads what it
# writes. A change to the generator or its options rebuilds only what it
# reaches. gen_mac.py stands in for any generator, in any language; the
# Bazel Central Registry has rule sets for many. --bits 8 writes the same
# unit as //examples:mac.
#
#   bazelisk build //examples/generated:mac_final
#
# `bazelisk run //:export` writes the Verilog it made into the export, as
# built; the generator stays here (docs/ramps.md).
load("@bazel_skylib//rules:build_test.bzl", "build_test")
load("@rules_python//python:defs.bzl", "py_binary")
load("//:openroad.bzl", "orfs_flow")

py_binary(
    name = "gen",
    srcs = ["gen_mac.py"],
    main = "gen_mac.py",
)

genrule(
    name = "mac_v",
    outs = ["mac.v"],
    cmd = "$(execpath :gen) --bits 8 > $@",
    tools = [":gen"],
)

orfs_flow(
    name = "mac",
    arguments = {
        "CORE_UTILIZATION": "40",
        "PLACE_DENSITY": "0.65",
    },
    sources = {
        "SDC_FILE": ["//examples:constraints.sdc"],
    },
    verilog_files = [":mac_v"],
)

# The generator and its wiring into the flow, through synthesis, without
# a second full flow in CI.
build_test(
    name = "mac_build_test",
    targets = [":mac_synth"],
)
