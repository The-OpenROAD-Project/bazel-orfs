load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "stage_power")

design(
    config = "config.mk",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

grt_netlist(
    name = "cmj_serv_grt_netlist",
    src = ":cmj_serv_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_serv_grt_power",
    src = ":cmj_serv_grt",
    saif = "//test/coremark_joule/sim:serv_rv32i_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
