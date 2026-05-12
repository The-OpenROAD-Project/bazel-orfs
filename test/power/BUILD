load("@rules_shell//shell:sh_binary.bzl", "sh_binary")
load("@rules_shell//shell:sh_test.bzl", "sh_test")
load("//:power.bzl", "verilator_saif")

# Fast wiring test for verilator_saif().
#
# Drive the rule against a hand-rolled mock simulator binary that
# instead of producing a real SAIF, writes its full argv into the file
# named by --trace-saif-file=<path>. The test then greps that file to
# confirm the rule passed:
#
#   --trace-saif-file=<the .saif output>     (genrule $@)
#   $(location stimulus)                      positional, resolved to a
#                                             real path under bazel-out
#   extra_args                                appended verbatim
#
# No real Verilator and no real OpenSTA — the mock binary is a 3-line
# shell script and the test runs in ~0s.

sh_binary(
    name = "mock_verilator",
    srcs = ["mock_verilator.sh"],
)

genrule(
    name = "mock_stimulus_gen",
    outs = ["mock_stimulus.bin"],
    cmd = "echo 'mock stimulus' > $@",
)

verilator_saif(
    name = "mock_run_saif",
    out = "mock_run_saif.saif",
    extra_args = "extra-arg-one extra-arg-two 0x42",
    saif_run = ":mock_verilator",
    stimulus = ":mock_stimulus.bin",
)

sh_test(
    name = "verilator_saif_argv_test",
    srcs = ["verilator_saif_argv_test.sh"],
    args = ["$(location :mock_run_saif.saif)"],
    data = [":mock_run_saif.saif"],
)

# Greps power.tcl / power_base.tcl / power_per_module.tcl for design-
# specific patterns that should NOT be in the upstream version (named-
# module SPEF branching, hardcoded SAIF_SCOPE hierarchies). Designs that
# need per-instance SPEF scoping pass SPEF_PATHS_TCL; SAIF_SCOPE is
# mandatory and supplied by the caller.
sh_test(
    name = "tcl_generic_test",
    srcs = ["tcl_generic_test.sh"],
    args = [
        "$(location //:power.tcl)",
        "$(location //:power_base.tcl)",
        "$(location //:power_per_module.tcl)",
    ],
    data = [
        "//:power.tcl",
        "//:power_base.tcl",
        "//:power_per_module.tcl",
    ],
)
