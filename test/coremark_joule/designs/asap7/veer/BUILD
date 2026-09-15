load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "stage_activity_audit", "stage_activity_sweep", "stage_power", "stage_power_units")

exports_files(["constraints.sdc"])

design(
    config = "config.mk",
    # Stages VeeR's own include fragments and the committed
    # configuration's headers into the sandbox for VERILOG_INCLUDE_DIRS,
    # without handing either to the frontend.
    user_sources = ["VEER_HEADERS"],
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The netlist the SAIF will be captured against, and the netlist power is
# reported on: the same one, from the same stage.
grt_netlist(
    name = "swerv_wrapper_grt_netlist",
    src = ":swerv_wrapper_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The energy half of the measurement, at global route.
stage_power(
    name = "swerv_wrapper_grt_power",
    src = ":swerv_wrapper_grt",
    saif = "//test/coremark_joule/sim:veer_rv32imc_saif",
    # The simulator wraps the design: TOP is Verilator's root, cm_soc the
    # harness SoC, and rvtop the instance of the hardened core.
    saif_scope = "TOP/cm_soc/rvtop",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Where the energy goes. This is the first design in the study whose
# memories are hardened, so the breakdown carries the L1 as macros
# alongside the pipeline units -- which is the split §8.1 of the paper
# asks for.
stage_power_units(
    name = "swerv_wrapper_grt_power_units",
    src = ":swerv_wrapper_grt",
    saif = "//test/coremark_joule/sim:veer_rv32imc_saif",
    saif_scope = "TOP/cm_soc/rvtop",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Which pins OpenSTA measured, and which it estimated.
stage_activity_audit(
    name = "swerv_wrapper_grt_activity",
    src = ":swerv_wrapper_grt",
    saif = "//test/coremark_joule/sim:veer_rv32imc_saif",
    saif_scope = "TOP/cm_soc/rvtop",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The bound on what the estimator could be worth.
stage_activity_sweep(
    name = "swerv_wrapper_grt_activity_sweep",
    src = ":swerv_wrapper_grt",
    saif = "//test/coremark_joule/sim:veer_rv32imc_saif",
    saif_scope = "TOP/cm_soc/rvtop",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
