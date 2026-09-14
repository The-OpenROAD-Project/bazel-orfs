load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "hier_probe", "stage_power")

# No memories_applied_test here: picorv32 has no convertible memory, so
# AUTO_MEMORIES is off and there is nothing for the guard to assert. The
# guard is wired on designs whose register file is a module.
design(
    config = "config.mk",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The netlist the SAIF will be captured against, and the netlist power is
# reported on: the same one, from the same stage.
grt_netlist(
    name = "cmj_picorv32_grt_netlist",
    src = ":cmj_picorv32_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The energy half of the measurement, at global route.
stage_power(
    name = "cmj_picorv32_grt_power",
    src = ":cmj_picorv32_grt",
    saif = "//test/coremark_joule/sim:picorv32_rv32im_saif",
    # The simulator wraps the design: TOP is Verilator's root, cm_soc the
    # harness SoC, and cpu the instance of the hardened core.
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

[
    hier_probe(
        name = "cmj_picorv32_hier_" + stage,
        src = ":cmj_picorv32_" + stage,
        stage = stage,
    )
    for stage in [
        "synth",
        "grt",
    ]
]
