load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "stage_power")

# §4.8's cross-check arm at 500 MHz: synthesis only, power on the
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
    saif = "//test/coremark_joule/sim:ibex_rv32imc_synth500_saif",
    saif_scope = "TOP/cm_soc/cpu",
    stage = "synth",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
