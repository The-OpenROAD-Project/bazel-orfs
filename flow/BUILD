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
        "//test/macro_select:__pkg__",
    ],
)

# Individual platform files an out-of-tree design names through
# $(PLATFORM_DIR). config_mk_parser turns such a reference into
# //flow:platforms/<platform>/<path>, and for a designs tree in this
# repository that label resolves here rather than in ORFS -- so each file
# a design needs gets an alias, the same way the PDK itself does above.
#
# Listed rather than globbed: ORFS's platform tree is an external
# repository, and a glob cannot see into one.
[
    alias(
        name = "platforms/asap7/" + path,
        actual = "@orfs//flow:platforms/asap7/" + path,
        visibility = [
            "//flow/designs:__subpackages__",
            "//test/coremark_joule/designs:__subpackages__",
        ],
    )
    for path in [
        # The SRAM shapes VeeR EH1's 16 kB instruction cache and 64 kB
        # DCCM resolve to. ORFS's own asap7/swerv_wrapper keeps these as
        # symlinks into exactly these paths.
        "lef/fakeram7_2048x39.lef",
        "lef/fakeram7_256x34.lef",
        "lef/fakeram7_64x21.lef",
        "lib/NLDM/fakeram7_2048x39.lib",
        "lib/NLDM/fakeram7_256x34.lib",
        "lib/NLDM/fakeram7_64x21.lib",
        # The block PDN grid XiangShan's BLOCKS= sub-macros are hardened
        # with (test/coremark_joule/designs/asap7/xiangshan/block.mk): a
        # core ring and straps for a hard macro, not a chip.
        "openRoad/pdn/BLOCK_grid_strategy.tcl",
        # And the parent's: M5/M6 stripes with a macro grid over every
        # block connecting its M5 pins to M6. The platform's config.mk
        # selects it when make sees BLOCKS; a bazel action never does, so
        # the parent's config.mk names it.
        "openRoad/pdn/BLOCKS_grid_strategy.tcl",
    ]
]
