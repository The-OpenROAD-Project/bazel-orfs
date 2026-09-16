load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "flop_power_probe", "grt_netlist", "stage_power")

# §4.8's cross-check arm at 100 MHz: synthesis only, power on the
# post-synthesis netlist with no wires and no clock tree. config.mk says
# what it is for.
exports_files(["constraints.sdc"])

design(
    config = "config.mk",
    user_sources = ["IBEX_HEADERS"],
    visibility = ["//test/coremark_joule:__subpackages__"],
)

grt_netlist(
    name = "cmj_ibex_synth_netlist",
    src = ":cmj_ibex_synth",
    stage = "synth",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_ibex_synth_power",
    src = ":cmj_ibex_synth",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_synth100_saif",
    saif_scope = "TOP/cm_soc/cpu",
    stage = "synth",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

flop_power_probe(
    name = "cmj_ibex_synth_flop_probe",
    src = ":cmj_ibex_synth",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_synth100_saif",
    saif_scope = "TOP/cm_soc/cpu",
)

# The same synthesis arm with the clock given the transition a clock tree
# would give it, so OpenSTA's 1/slew clamp on the unbuffered clock net
# does not decide the flops' energy. 20 ps is a round post-CTS figure.
stage_power(
    name = "cmj_ibex_synth_slew20_power",
    src = ":cmj_ibex_synth",
    clock_transition_ps = 20,
    saif = "//test/coremark_joule/sim:ibex_rv32imc_synth100_saif",
    saif_scope = "TOP/cm_soc/cpu",
    stage = "synth",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
