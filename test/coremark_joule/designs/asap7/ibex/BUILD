load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "period_probe", "stage_activity_audit", "stage_activity_sweep", "stage_power")
load("//test/coremark_joule/scripts:synth_crosscheck.bzl", "synth_crosscheck")

exports_files(["constraints.sdc"])

design(
    config = "config.mk",
    # Stages the vendored OpenTitan headers into the sandbox for
    # VERILOG_INCLUDE_DIRS without handing them to the frontend.
    user_sources = ["IBEX_HEADERS"],
    visibility = ["//test/coremark_joule:__subpackages__"],
)

grt_netlist(
    name = "cmj_ibex_grt_netlist",
    src = ":cmj_ibex_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# 5.3's calibration point: what the parasitics estimate costs.
#
# The study reports every number at global route, where parasitics are
# predicted from the global routes rather than extracted. These two
# targets put a size on that choice, and they are a pair on purpose:
# same 6_final ODB, same SAIF, same everything -- one reads the
# extracted SPEF, the other calls estimate_parasitics -global_routing on
# the very netlist the SPEF describes. The difference between them is
# the parasitics model alone.
#
# Comparing the extracted number against the reported grt number is the
# other half, and answers a different question: what screening before
# detailed route costs end to end, netlist changes included.
#
# One design. 5.3 says why a sweep over all four is further work rather
# than a result.
stage_power(
    name = "cmj_ibex_final_power_extracted",
    src = ":cmj_ibex_final",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_saif",
    saif_scope = "TOP/cm_soc/cpu",
    spef = "6_final.spef",
    stage = "final",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_ibex_final_power_estimated",
    src = ":cmj_ibex_final",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_saif",
    saif_scope = "TOP/cm_soc/cpu",
    stage = "final",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_ibex_grt_power",
    src = ":cmj_ibex_grt",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_saif",
    # u_core, not cpu: the ibex wrapper names its core instance
    # differently from the other two. A wrong scope is not an error --
    # OpenSTA falls back to default activity -- so cm_per_joule compares
    # the SAIF-driven and vectorless reports and fails when they match.
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Which pins OpenSTA measured, and which it estimated.
#
# `report_power -saif` never fails for want of activity: an unannotated
# pin is estimated, and the estimate is indistinguishable from a
# measurement in the report. The audit enumerates and classifies every
# pin the SAIF did not reach; the sweep bounds what they could be worth.
stage_activity_audit(
    name = "cmj_ibex_grt_activity",
    src = ":cmj_ibex_grt",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The bound. `set_power_activity -input` is the only way a density
# OpenSTA invented enters the design; sweeping it from "never toggles"
# to "toggles every cycle" must leave the SAIF-driven total where it is,
# while moving the vectorless one -- which is the positive control that
# makes the null result mean something.
stage_activity_sweep(
    name = "cmj_ibex_grt_activity_sweep",
    src = ":cmj_ibex_grt",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The minimum clock period, reg2reg only. See §3.8.
period_probe(
    name = "cmj_ibex_period",
    src = ":cmj_ibex_grt",
)

# §4.8's cross-check, arm one: this design's own synthesis netlist at its
# own 1200 ps period, power with no wires and no clock tree. Against the
# global-route point it isolates the stage; against the ibex_synth100 and
# ibex_synth500 packages it isolates the period.
grt_netlist(
    name = "cmj_ibex_synth_netlist",
    src = ":cmj_ibex_synth",
    stage = "synth",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_ibex_synth_power",
    src = ":cmj_ibex_synth",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_synth_saif",
    saif_scope = "TOP/cm_soc/cpu",
    stage = "synth",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The table §4.8 quotes: core-only energy per CoreMark iteration at each
# arm, next to the published 65 nm rows.
synth_crosscheck(
    name = "ibex_synth_crosscheck",
    arms = {
        "grt, 1200 ps": ":cmj_ibex_grt_power",
        "synth, 1200 ps": ":cmj_ibex_synth_power",
        "synth, 2000 ps": "//test/coremark_joule/designs/asap7/ibex_synth500:cmj_ibex_synth_power",
        "synth, 10000 ps": "//test/coremark_joule/designs/asap7/ibex_synth100:cmj_ibex_synth_power",
    },
    per_mhz = "//test/coremark_joule/sim:ibex_rv32imc_per_mhz",
    periods_ps = {
        "grt, 1200 ps": 1200,
        "synth, 1200 ps": 1200,
        "synth, 2000 ps": 2000,
        "synth, 10000 ps": 10000,
    },
)
