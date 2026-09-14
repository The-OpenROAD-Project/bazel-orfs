load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist")

design(
    config = "config.mk",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

grt_netlist(
    name = "cmj_serv_grt_netlist",
    src = ":cmj_serv_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
