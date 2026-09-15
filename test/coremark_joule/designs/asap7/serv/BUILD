load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "hier_probe", "period_probe", "stage_activity_audit", "stage_activity_sweep", "stage_power", "stage_power_units")

exports_files(["constraints.sdc"])

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

# Which pins OpenSTA measured, and which it estimated.
#
# `report_power -saif` never fails for want of activity: an unannotated
# pin is estimated, and the estimate is indistinguishable from a
# measurement in the report. The audit enumerates and classifies every
# pin the SAIF did not reach; the sweep bounds what they could be worth.
stage_activity_audit(
    name = "cmj_serv_grt_activity",
    src = ":cmj_serv_grt",
    saif = "//test/coremark_joule/sim:serv_rv32i_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The bound. `set_power_activity -input` is the only way a density
# OpenSTA invented enters the design; sweeping it from "never toggles"
# to "toggles every cycle" must leave the SAIF-driven total where it is,
# while moving the vectorless one -- which is the positive control that
# makes the null result mean something.
stage_activity_sweep(
    name = "cmj_serv_grt_activity_sweep",
    src = ":cmj_serv_grt",
    saif = "//test/coremark_joule/sim:serv_rv32i_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The minimum clock period, reg2reg only. See §3.8.
period_probe(
    name = "cmj_serv_period",
    src = ":cmj_serv_grt",
)
