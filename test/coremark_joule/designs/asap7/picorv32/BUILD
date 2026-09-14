load("@coremark_joule_designs//:designs.bzl", "design")
load("//test/coremark_joule/flow:power.bzl", "grt_netlist")

# No memories_applied_test here: picorv32 has no convertible memory, so
# AUTO_MEMORIES is off and there is nothing for the guard to assert. The
# guard is wired on designs whose register file is a module.
design(
    config = "config.mk",
    visibility = ["//test/coremark_joule:__subpackages__"],
)

# The netlist the SAIF will be captured against, and the netlist power is
# reported on: the same one, from the same stage.
grt_netlist(
    name = "cmj_picorv32_grt_netlist",
    src = ":cmj_picorv32_grt",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
