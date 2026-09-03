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

load("//:orfs_design_builds.bzl", "RECORDED_BUILDS")

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
    # flow.tcl as a label, so the floorplan derivation's drift test can
    # compare its duplicated stage sequence against the one that runs.
    #
    # This patch edits ORFS's own flow/BUILD, so it stops applying once
    # ORFS deletes that file. _GENERATE_FLOW_BUILD therefore exports
    # scripts/flow.tcl too, and //test:orfs_flow_build_test requires it.
    # Both mechanisms are needed: the patch covers an ORFS that still
    # ships flow/BUILD, the generated file covers one that does not.
    Label("//patches:0047-orfs-export-flow-tcl.patch"),
    # flow.sh spells out run_command.py by hand instead of going through
    # RUN_CMD, so an override reaches every logged target except the
    # stage logs. --@bazel-orfs//:log_timestamps overrides RUN_CMD.
    Label("//patches:0048-orfs-flow-sh-honor-run-cmd.patch"),
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
        "scripts/flow.tcl",
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

# flow/designs/design.bzl, written unconditionally rather than patched.
#
# This file is a pure re-export of design() and files() -- bazel-orfs
# owns every line of it -- so writing it is both simpler and more robust
# than patching it. A patch has to match what ORFS ships, which means it
# breaks the moment ORFS changes or deletes the file; that is exactly the
# transition we are trying to make survivable. This replaces patch
# 0046-orfs-design-dsl-reexport.patch.
#
# Unconditional, not absent-only, and deliberately so: while ORFS still
# ships its own copy that copy is the problem. It passed a `blender`
# argument for some time after bazel-orfs removed the parameter, so every
# @orfs design package failed to load with
#   Error: orfs_design() got unexpected keyword argument: blender
_WRITE_DESIGN_BZL = """
mkdir -p flow/designs
cat > flow/designs/design.bzl <<'ORFS_DESIGN_BZL_EOF'
'''BUILD boilerplate for flow/designs/.

Written by bazel-orfs: see orfs_source.bzl. The DSL itself lives in
bazel-orfs (private/design_dsl.bzl), bound to this consumer's DESIGNS by
the generated @orfs_designs//:designs.bzl. Keeping it there keeps it in
step with the rules it drives.

Design BUILD files are unchanged -- they still load design() and files()
from here.
'''

load("@orfs_designs//:designs.bzl", _design = "design", _files = "files")

design = _design

files = _files
ORFS_DESIGN_BZL_EOF
"""

# The design BUILD files that cannot be generated, written back
# absent-only from a recorded copy.
#
# A files() group name is decided by which label *other* designs'
# config.mk files reference, not by the directory's contents -- src/cva6
# declares files("verilog") while holding no .v or .sv at all, and
# prim/rtl holds both .sv and .svh but declares files("include"). So
# these 117 files are carried as data rather than guessed at. That is the
# distinction: generating a name that happens to be wrong renames a
# target and breaks a reference in an unrelated design's config, far from
# the guess.
#
# Recorded by ./record_orfs_builds.py from a clean ORFS checkout, which
# refuses a dirty tree -- a first run against a campaign branch captured
# 119 files, the two extras being uncommitted local edits.
#
# Absent-only, so this is a no-op against an ORFS that still ships them
# and correct against one that has deleted them. Together with the
# config.mk generator and _GENERATE_FLOW_BUILD, it means ORFS need carry
# no bazel files at all.
#
# The heredoc is single-quoted, so no shell expansion touches content
# that is full of $(MAKE_VARIABLES); record_orfs_builds.py rejects any
# file containing the delimiter.
def _write_recorded_builds():
    """Shell to write every recorded BUILD file that is absent.

    Returns:
      A single shell script string for patch_cmds.
    """
    parts = []
    for path in sorted(RECORDED_BUILDS):
        parts.append(
            ("if [ ! -e {path} ] && [ ! -e {dir}/BUILD.bazel ] && " +
             "[ ! -e {dir}/BUILD ]; then\n" +
             "mkdir -p {dir}\n" +
             "cat > {path} <<'ORFS_RECORDED_BUILD_EOF'\n" +
             "{content}ORFS_RECORDED_BUILD_EOF\n" +
             "fi\n").format(
                path = path,
                dir = path.rsplit("/", 1)[0],
                content = RECORDED_BUILDS[path],
            ),
        )
    return "".join(parts)

ORFS_PATCH_CMDS = [
    _WRITE_DESIGN_BZL,
    _write_recorded_builds(),
    _GENERATE_DESIGN_BUILDS.format(
        platforms = " ".join(ORFS_BAZEL_PLATFORMS),
    ),
    _GENERATE_FLOW_BUILD,
]

def orfs_archive_args(commit, integrity, urls = []):
    """http_archive arguments for an ORFS commit.

    Args:
      commit: the ORFS commit to fetch.
      integrity: Subresource Integrity string for the tarball.
      urls: optional override for where the tarball comes from. Empty
        means the canonical ORFS GitHub archive for `commit`.

    Returns:
      A dict of http_archive keyword arguments.
    """
    return {
        "integrity": integrity,
        "patch_args": ["-p1"],
        "patch_cmds": ORFS_PATCH_CMDS,
        "patches": ORFS_PATCHES,
        "strip_prefix": ORFS_STRIP_PREFIX_TEMPLATE.format(commit),
        "urls": urls if urls else [ORFS_URL_TEMPLATE.format(commit)],
    }
