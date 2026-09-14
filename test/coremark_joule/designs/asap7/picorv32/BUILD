load("@coremark_joule_designs//:designs.bzl", "design")

# No memories_applied_test here: picorv32 has no convertible memory, so
# AUTO_MEMORIES is off and there is nothing for the guard to assert. The
# guard is wired on designs whose register file is a module.
design(
    config = "config.mk",
    visibility = ["//test/coremark_joule:__subpackages__"],
)
