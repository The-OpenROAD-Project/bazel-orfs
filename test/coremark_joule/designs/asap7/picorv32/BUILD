load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "hier_probe", "period_probe", "stage_activity_audit", "stage_activity_sweep", "stage_power")
load("//test/coremark_joule/flow:seeds.bzl", "seed_variants")

# No memories_applied_test here: picorv32 has no convertible memory, so
# AUTO_MEMORIES is off and there is nothing for the guard to assert. The
# guard is wired on designs whose register file is a module.
exports_files(["constraints.sdc"])

design(
    config = "config.mk",
    # §5.13's placement-seed ensemble: four more draws of global placement
    # from this design's own floorplan, each taken through the same SAIF
    # and power chain as the design itself.
    extra = seed_variants(
        max_renames = 0,
        saif_prefix = "//test/coremark_joule/sim:picorv32_rv32im",
        saif_scope = "TOP/cm_soc/cpu",
    ),
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

# Which pins OpenSTA measured, and which it estimated.
#
# `report_power -saif` never fails for want of activity: an unannotated
# pin is estimated, and the estimate is indistinguishable from a
# measurement in the report. The audit enumerates and classifies every
# pin the SAIF did not reach; the sweep bounds what they could be worth.
stage_activity_audit(
    name = "cmj_picorv32_grt_activity",
    src = ":cmj_picorv32_grt",
    saif = "//test/coremark_joule/sim:picorv32_rv32im_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The bound. `set_power_activity -input` is the only way a density
# OpenSTA invented enters the design; sweeping it from "never toggles"
# to "toggles every cycle" must leave the SAIF-driven total where it is,
# while moving the vectorless one -- which is the positive control that
# makes the null result mean something.
stage_activity_sweep(
    name = "cmj_picorv32_grt_activity_sweep",
    src = ":cmj_picorv32_grt",
    saif = "//test/coremark_joule/sim:picorv32_rv32im_saif",
    saif_scope = "TOP/cm_soc/cpu",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The minimum clock period, reg2reg only. See §3.8.
period_probe(
    name = "cmj_picorv32_period",
    src = ":cmj_picorv32_grt",
)
