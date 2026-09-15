load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist", "hier_probe", "stage_power", "stage_power_units")

design(
    config = "config.mk",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

grt_netlist(
    name = "cmj_xiangshan_grt_netlist",
    src = ":XSCore_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# XiangShan is the core the per-unit breakdown is for: its modules are
# monomorphic, so unlike SERV's parameterized ones they should reach the
# ODB with their names intact, and its hierarchy maps onto the categories
# the literature reports.
stage_power_units(
    name = "cmj_xiangshan_grt_power_units",
    src = ":XSCore_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2/core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

stage_power(
    name = "cmj_xiangshan_grt_power",
    src = ":XSCore_grt",
    saif = "//test/coremark_joule/sim:xiangshan_rv64gc_saif",
    saif_scope = "TOP/cm_soc/inner/soc/core_with_l2/core",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# Whether the kept module boundaries survived into the ODB. Cheap, and
# the failure it catches is silent: the flow completes, the netlist is
# valid, and the breakdown simply comes back empty.
[
    hier_probe(
        name = "cmj_xiangshan_hier_" + stage,
        src = ":XSCore_" + stage,
        stage = stage,
    )
    for stage in [
        "synth",
        "grt",
    ]
]
