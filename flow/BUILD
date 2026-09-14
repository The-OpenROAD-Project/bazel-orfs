# PDK labels for this repository's own config.mk designs trees.
#
# The config.mk DSL (private/orfs_design.bzl) is what every ORFS design
# goes through, and a design's PDK is //flow:<platform>. This package
# supplies those labels by aliasing ORFS's, so a designs tree inside this
# repository can go through the same path.
#
# Two trees use it. The fixtures under flow/designs/ mirror ORFS's layout
# so the DSL can be exercised here in seconds rather than only against
# real ORFS designs that take minutes (see //test:dsl_* and test/BUILD).
# //test/coremark_joule/designs is a study's own designs tree, which is
# the case orfs_designs()'s designs_dir attribute exists to allow.
alias(
    name = "asap7",
    actual = "@orfs//flow:asap7",
    visibility = [
        "//flow/designs:__subpackages__",
        "//test/coremark_joule/designs:__subpackages__",
    ],
)
