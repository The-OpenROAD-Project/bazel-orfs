load("@rules_shell//shell:sh_test.bzl", "sh_test")

# Root of this study's config.mk designs.
#
# MODULE.bazel points a third orfs_designs() instance at this file. The
# repository rule parses every config.mk under <platform>/ here exactly
# as it parses ORFS's, so these designs get the same generated flow
# targets -- and the same _auto_floorplan_data / _auto_floorplan_pin
# derivation -- without the study having to patch an ORFS checkout.
exports_files(["BUILD"])

# Every design's SDC, checked against the constraint model of §3.8: no
# set_input_delay or set_output_delay anywhere, and all three IO budgets
# stated so the platform's 80 ps default never applies.
#
# Listed rather than globbed: each design under asap7/ is its own
# package, and a glob cannot cross a package boundary -- it would match
# nothing and the test would pass by checking no files at all. A design
# added later has to be added here, and //test:orfs_platforms_test is
# not going to notice if it is not.
SDC_FILES = [
    "//test/coremark_joule/designs/asap7/picorv32:constraints.sdc",
    "//test/coremark_joule/designs/asap7/serv:constraints.sdc",
    "//test/coremark_joule/designs/asap7/ibex:constraints.sdc",
    "//test/coremark_joule/designs/asap7/veer:constraints.sdc",
    # §4.8's synthesis-only cross-check arms: the ibex SDC at two other periods.
    "//test/coremark_joule/designs/asap7/ibex_synth100:constraints.sdc",
    "//test/coremark_joule/designs/asap7/ibex_synth500:constraints.sdc",
]

sh_test(
    name = "sdc_model_test",
    size = "small",
    srcs = ["//test/coremark_joule/scripts:run_check_sdc.sh"],
    args = ["$(location //test/coremark_joule/scripts:check_sdc)"] +
           ["$(location {})".format(sdc) for sdc in SDC_FILES],
    data = SDC_FILES + [
        "//test/coremark_joule/scripts:check_sdc",
    ],
)
