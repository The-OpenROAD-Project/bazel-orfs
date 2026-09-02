"""Where the ORFS tarball comes from, and what bazel-orfs does to it.

ORFS is consumed as an `http_archive` created by the `orfs_repositories`
module extension, not as a `bazel_dep`. The reason is a bzlmod rule:
`patches` on `archive_override`/`git_override` is honoured **only from
the root module**. So while ORFS is a module dependency, the patching
lands on whoever happens to be root -- OpenROAD would have to carry ORFS
patches, and bazel-orfs, as a non-root module, could not patch ORFS at
all.

Module extensions run for every build regardless of which module
declared them, so a repository created here is patched by bazel-orfs's
code either way. A root module picks the *version* with

    orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
    orfs.source(commit = "...", integrity = "sha256-...")

and carries no patches, no strip_prefix and no URL construction.

See docs/plans/orfs-as-file-store.md for the full design.
"""

ORFS_URL_TEMPLATE = "https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/archive/{}.tar.gz"

ORFS_STRIP_PREFIX_TEMPLATE = "OpenROAD-flow-scripts-{}"

# Platforms parsed into DESIGNS, and therefore the only platforms whose
# designs can have flow targets. Must match the `platforms` list passed
# to orfs_designs(). Generating a BUILD under a platform outside this
# list -- gf12 or gt2n, which ORFS exposes no BUILD files for at all --
# invents a package whose design() call DESIGNS cannot resolve.
ORFS_BAZEL_PLATFORMS = [
    "asap7",
    "gf180",
    "ihp-sg13g2",
    "nangate45",
    "sky130hd",
    "sky130hs",
]

ORFS_PATCHES = [
    Label("//patches:0037-orfs-single-writer-1_synth-sdc.patch"),
    Label("//patches:0039-orfs-slang-plugin-fallback.patch"),
    # The config.mk BUILD DSL (design(), files()) lives here, in
    # private/design_dsl.bzl, bound to this consumer's DESIGNS by the
    # generated @orfs_designs//:designs.bzl. ORFS keeps a re-export for
    # the BUILD files it still ships, so those are untouched.
    #
    # Owning the DSL keeps it in step with the rules it drives. It had
    # drifted: ORFS passed a `blender` argument for some time after
    # bazel-orfs removed the parameter, so every @orfs design package
    # failed to load with
    #   Error: orfs_design() got unexpected keyword argument: blender
    # The CI step that loads every @orfs design package guards against a
    # repeat.
    Label("//patches:0046-orfs-design-dsl-reexport.patch"),
]

# Generate the BUILD file for any design directory that has a config.mk
# and no BUILD, so ORFS need not carry ~56 identical
# `design(config = "config.mk")` files whose only reader is bazel -- a
# build system ORFS does not itself use. See docs/orfs-design-builds.md
# for the ORFS-side cleanup this enables.
#
# config.mk only, deliberately. The other ~89 design BUILDs declare a
# files() group -- "verilog", "include", "lef", "lib", "gds" -- and which
# group a directory needs is NOT derivable from its contents:
#
#   * src/cva6 and src/mempool_group/rtl/axi declare files("verilog")
#     while holding no .v/.sv at all (only .svh, or nothing). The
#     filegroup is legitimately empty -- files() globs with allow_empty
#     -- but the label still has to exist, because another design's
#     config.mk references it.
#   * ibex_sv/vendor/.../prim/rtl holds both .sv and .svh and declares
#     files("include"), not files("verilog").
#
# The group is decided by what other configs reference, which lives in
# the config.mk corpus rather than in the directory. Guessing it wrong
# renames a target and breaks those references at the far end.
# test/orfs_design_builds_test.py holds this line: it compares the rules
# below against every canonical BUILD ORFS still ships.
#
# Absent only, never overwritten. That is the safety argument: a design
# with a hand-written BUILD keeps it by virtue of having one, so there is
# no keep-list to maintain and nothing is silently clobbered. It also
# makes this both forward- and backward-compatible: against today's ORFS
# every BUILD exists and this is a no-op, and after the cleanup the
# deleted ones come back identical.
#
# The generated file loads from @orfs_designs//:designs.bzl rather than
# //flow/designs:design.bzl so it does not depend on ORFS keeping the
# re-export.
#
# The walk is a `find` rather than a `$platform/*` glob because
# hierarchical flows nest a block's design directory inside its parent's
# -- asap7/riscv32i-mock-sram/fakeram7_256x32,
# gf180/uart-blocks/uart_rx, ihp-sg13g2/i2c-gpio-expander/I2cDeviceCtrl.
# A one-level glob silently missed those three, which only showed up on a
# run against an ORFS with the BUILD files actually deleted.
#
# Drift here is caught by the "Load @orfs design packages" CI step.
_GENERATE_DESIGN_BUILDS = """
for platform in {platforms}; do
  [ -d "flow/designs/$platform" ] || continue
  find "flow/designs/$platform" -type f -name config.mk | sort | while read -r cfg; do
    d=$(dirname "$cfg")
    if [ -e "$d/BUILD" ] || [ -e "$d/BUILD.bazel" ]; then continue; fi
    {{
      echo '# Generated by bazel-orfs: see orfs_source.bzl.'
      echo 'load("@orfs_designs//:designs.bzl", "design")'
      echo ''
      echo 'design(config = "config.mk")'
    }} > "$d/BUILD"
  done
done
"""

# `flow/BUILD` and `flow/util/BUILD`, generated when absent, for the same
# reason and by the same rule as the design BUILDs above: ORFS should not
# have to carry bazel files for a build system it does not use.
#
# These two packages are the whole non-design coupling surface. Every
# `@orfs//` label bazel-orfs resolves comes from them:
#
#   @orfs//flow:<pdk>                     orfs_pdk targets
#   @orfs//flow:makefile                  filegroup
#   @orfs//flow:makefile_yosys            filegroup
#   @orfs//flow:scripts/synth.tcl         exports_files
#   @orfs//flow:scripts/variables.yaml    exports_files
#   @orfs//flow:platforms/<pdk>/...       exports_files glob
#
# `orfs_pdk` has to be declared inside @orfs because a glob() only sees
# its own repository. Authoring the BUILD here is what lets the glob run
# in the ORFS repo context while the rule and the per-platform extension
# map -- a statement about how these rules consume a PDK, not about the
# files -- live next to the rules.
#
# Deliberately not reproduced: ORFS's own bazel-only conveniences, which
# nothing here consumes and which its CI does not run (no ORFS workflow
# invokes bazel) -- the AUTO_MEMORIES py_library/py_test/test_suite,
# synDashboard, compile_pip_requirements and genMetrics_test. Generating
# them would mean maintaining ORFS's test wiring from the outside.
#
# One improvement over the file it replaces: scripts/variables.yaml is
# exported. bazel-orfs already references that label, and it works today
# only because load_json_file is a repository rule reading through
# repository_ctx.path(), which resolves a path on disk rather than a
# build-graph dependency.
#
# Single-quoted heredocs: no shell expansion at all, so the content is
# byte-literal. The design-BUILD generator shipped broken twice on quote
# escaping, and this file is two orders of magnitude longer.
_GENERATE_FLOW_BUILD = """
if [ ! -e flow/BUILD ] && [ ! -e flow/BUILD.bazel ]; then
cat > flow/BUILD <<'ORFS_FLOW_BUILD_EOF'
# Generated by bazel-orfs: see orfs_source.bzl.
load("@bazel-orfs//:openroad.bzl", "orfs_pdk")

# Individual platform files as public source labels, so a design in
# another package can reference e.g.
# //flow:platforms/asap7/verilog/fakeram7_64x28.sv directly. This is the
# label form config_mk_parser produces for VERILOG_FILES /
# ADDITIONAL_LEFS / ADDITIONAL_LIBS entries pointing at platform files.
exports_files(
    glob(
        ["platforms/**/*"],
        exclude = [
            "platforms/**/BUILD",
            "platforms/**/BUILD.bazel",
        ],
    ),
    visibility = ["//visibility:public"],
)

exports_files(
    [
        "scripts/synth.tcl",
        "scripts/variables.yaml",
    ],
    visibility = ["//visibility:public"],
)

MAKEFILE_SHARED = [
    "scripts/variables.json",
    "scripts/*.py",
    "scripts/memories/*.py",
    "scripts/*.sh",
    "scripts/*.yaml",
    "scripts/*.mk",
]

MAKEFILE_SHARED_EXCLUDE = ["scripts/memories/*_test.py"]

filegroup(
    name = "makefile_yosys",
    srcs = ["Makefile"],
    data = glob(
        MAKEFILE_SHARED + [
            "scripts/*.script",
            "scripts/*.v",
            "scripts/util.tcl",
            "scripts/synth*.tcl",
            "scripts/synth*.v",
            "platforms/common/**/*.v",
        ],
        exclude = MAKEFILE_SHARED_EXCLUDE,
    ) + ["//flow/util:makefile_yosys"],
    visibility = ["//visibility:public"],
)

filegroup(
    name = "makefile",
    srcs = ["Makefile"],
    data = glob(
        MAKEFILE_SHARED + [
            "scripts/*.tcl",
            "platforms/common/**/*.v",
        ],
        exclude = MAKEFILE_SHARED_EXCLUDE,
    ) + ["//flow/util:makefile"],
    visibility = ["//visibility:public"],
)

PDK_EXTS = {
    "asap7": ["cfg", "gds", "lef", "lib", "lib.gz", "lyt", "mk", "rules", "sdc", "sv", "tcl", "v"],
    "gf180": ["cfg", "gds", "lef", "lib.gz", "lyt", "mk", "rules", "tcl", "v"],
    "ihp-sg13g2": ["gds", "json", "lef", "lib", "lyt", "mk", "rules", "tcl", "v"],
    "nangate45": ["cfg", "gds", "lef", "lib", "lyt", "mk", "rules", "tcl", "v"],
    "sky130hd": ["gds", "lef", "lib", "lyt", "mk", "rules", "tcl", "tlef", "v"],
    "sky130hs": ["gds", "lef", "lib", "lyt", "mk", "rules", "tcl", "tlef", "v"],
}

PDK_LIB_EXTS = {
    "asap7": ["lib", "lib.gz"],
    "gf180": ["lib.gz"],
}

[orfs_pdk(
    name = pdk,
    srcs = glob([
        "platforms/{pdk}/**/*.{ext}".format(ext = ext, pdk = pdk)
        for ext in PDK_EXTS[pdk]
    ] + ["platforms/common/**/*.v"]),
    config = ":platforms/{pdk}/config.mk".format(pdk = pdk),
    libs = glob([
        "platforms/{pdk}/**/*.{ext}".format(ext = ext, pdk = pdk)
        for ext in PDK_LIB_EXTS.get(pdk, ["lib"])
    ]),
    visibility = ["//visibility:public"],
) for pdk in PDK_EXTS]
ORFS_FLOW_BUILD_EOF
fi

if [ ! -e flow/util/BUILD ] && [ ! -e flow/util/BUILD.bazel ]; then
cat > flow/util/BUILD <<'ORFS_FLOW_UTIL_BUILD_EOF'
# Generated by bazel-orfs: see orfs_source.bzl.
filegroup(
    name = "makefile",
    srcs = glob(
        [
            "*.mk",
            "*.py",
            "*.sh",
        ],
        exclude = ["*_test.py"],
    ),
    visibility = ["//visibility:public"],
)

filegroup(
    name = "makefile_yosys",
    srcs = glob(["*.mk"]),
    visibility = ["//visibility:public"],
)
ORFS_FLOW_UTIL_BUILD_EOF
fi
"""

ORFS_PATCH_CMDS = [
    _GENERATE_DESIGN_BUILDS.format(
        platforms = " ".join(ORFS_BAZEL_PLATFORMS),
    ),
    _GENERATE_FLOW_BUILD,
]

def orfs_archive_args(commit, integrity):
    """http_archive arguments for an ORFS commit.

    Args:
      commit: the ORFS commit to fetch.
      integrity: Subresource Integrity string for the tarball.

    Returns:
      A dict of http_archive keyword arguments.
    """
    return {
        "integrity": integrity,
        "patch_args": ["-p1"],
        "patch_cmds": ORFS_PATCH_CMDS,
        "patches": ORFS_PATCHES,
        "strip_prefix": ORFS_STRIP_PREFIX_TEMPLATE.format(commit),
        "urls": [ORFS_URL_TEMPLATE.format(commit)],
    }
