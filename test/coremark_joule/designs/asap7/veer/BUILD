load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "dup_inst_probe", "grt_netlist", "period_probe", "physical_probe", "stage_activity_audit", "stage_activity_sweep", "stage_power", "stage_power_units", "stage_sdf")
load("//test/coremark_joule/flow:seeds.bzl", "seed_variants")

exports_files(["constraints.sdc"])

design(
    config = "config.mk",
    # §5.13's placement-seed ensemble: four more draws of global placement
    # from this design's own floorplan, each taken through the same SAIF
    # and power chain as the design itself.
    extra = seed_variants(
        # write_verilog's non-injective name mapping (§5.12). One collision on
        # the FakeRAM floorplan, two on the scaler's -- both clock-gate
        # latches -- and the seed variants will each draw their own. Four is
        # a budget the ensemble can live under; the paper reports the count
        # measured on the pinned design.
        max_renames = 4,
        saif_prefix = "//test/coremark_joule/sim:veer_rv32imc",
        saif_scope = "TOP/cm_soc/rvtop",
    ),
    # Stages VeeR's own include fragments and the committed
    # configuration's headers into the sandbox for VERILOG_INCLUDE_DIRS,
    # without handing either to the frontend.
    user_arguments = ["SYNTH_POST_HIERARCHY_SCRIPTS"],
    user_sources = [
        "VEER_HEADERS",
        "VEER_ICG_MAP",
    ],
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The netlist the SAIF will be captured against, and the netlist power is
# reported on: the same one, from the same stage.
# One duplicate instance name, declared. OpenROAD's write_verilog gives
# two different AND2x2 clock cells -- on clknet_leaf_24_clk_i and
# clknet_leaf_152_clk_i -- the same name `_131758_` inside
# ifu_bp_ctl$swerv_wrapper.swerv.ifu.bp, one collision among that
# module's 88,520 instances. See scripts/uniquify_netlist.py.
grt_netlist(
    name = "swerv_wrapper_grt_netlist",
    src = ":swerv_wrapper_grt",
    # write_verilog's non-injective name mapping (§5.12). One collision on
    # the FakeRAM floorplan, two on the scaler's -- both clock-gate
    # latches -- and the seed variants will each draw their own. Four is
    # a budget the ensemble can live under; the paper reports the count
    # measured on the pinned design.
    max_renames = 4,
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The per-instance delays, for the glitch measurement (5.2b). VeeR has
# four instances of exu_alu_ctl in one hardening, which is a within-
# design measurement of how much of glitch is the implementation (2.4).
stage_sdf(
    name = "swerv_wrapper_grt_sdf",
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

# The two clock nets whose AND2x2 cells write_verilog gave the same name.
dup_inst_probe(
    name = "swerv_wrapper_dup_inst",
    src = ":swerv_wrapper_grt",
    nets = [
        "clknet_leaf_24_clk_i",
        "clknet_leaf_152_clk_i",
    ],
)

# The minimum clock period, reg2reg only. See §3.8.
period_probe(
    name = "swerv_wrapper_period",
    src = ":swerv_wrapper_grt",
)

# The measured side of the literature table. See §4.9.
physical_probe(
    name = "swerv_wrapper_physical",
    src = ":swerv_wrapper_grt",
    visibility = ["//test/coremark_joule:__pkg__"],
)
