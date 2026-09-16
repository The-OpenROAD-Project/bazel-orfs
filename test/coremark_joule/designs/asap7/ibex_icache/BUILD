load("@coremark_joule_designs//:designs.bzl", "design")

# A guard, not a measurement. config.mk says why ibex's reported point
# has the cache off; this design keeps the machinery that turns it on
# from rotting -- the ASAP7 prim_ram_1p, the two cache-RAM macros, and
# a kept-module list that matches a configuration with no prefetch
# buffer. Global route is as far as it needs to go: by then the macros
# have been generated, converted, placed and routed, which is all this
# is asserting.
exports_files(["constraints.sdc"])

design(
    config = "config.mk",
    # Stages the vendored OpenTitan headers into the sandbox for
    # VERILOG_INCLUDE_DIRS without handing them to the frontend.
    user_sources = ["IBEX_HEADERS"],
    visibility = ["//test/coremark_joule:__subpackages__"],
)
