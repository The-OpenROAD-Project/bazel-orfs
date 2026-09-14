load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "hier_probe", "stage_power", "stage_power_units")

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

# SERV is the core the per-unit breakdown is for: its RTL is one module
# per architectural function, so almost nothing lands in "other".
stage_power_units(
    name = "cmj_serv_grt_power_units",
    src = ":cmj_serv_grt",
    saif = "//test/coremark_joule/sim:serv_rv32i_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

[
    hier_probe(
        name = "cmj_serv_hier_" + stage,
        src = ":cmj_serv_" + stage,
        stage = stage,
    )
    for stage in [
        "synth",
        "grt",
    ]
]
