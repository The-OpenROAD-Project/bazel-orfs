load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "stage_power")

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

stage_power(
    name = "cmj_ibex_grt_power",
    src = ":cmj_ibex_grt",
    saif = "//test/coremark_joule/sim:ibex_rv32imc_saif",
    # u_core, not cpu: the ibex wrapper names its core instance
    # differently from the other two. A wrong scope is not an error --
    # OpenSTA falls back to default activity -- so cm_per_joule compares
    # the SAIF-driven and vectorless reports and fails when they match.
    saif_scope = "TOP/cm_soc/u_core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
