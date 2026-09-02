"""The config.mk BUILD DSL: design() and files().

These macros are the whole BUILD body of an ORFS design package. They used
to live in ORFS as flow/designs/design.bzl, which meant the DSL evolved on
one side of the module boundary while the rules it drives evolved on the
other -- and the two drifted: ORFS kept passing a `blender` argument for
some time after bazel-orfs removed the parameter, so every @orfs design
package failed to load with

    Error: orfs_design() got unexpected keyword argument: blender

Owning the DSL here keeps it in step with orfs_design() by construction.
ORFS retains only a re-export, so its ~100 design BUILD files are
unchanged.

The DESIGNS dict cannot live here: it is generated per consumer from that
consumer's designs_dir. So design() takes it as an argument and the
generated @orfs_designs//:designs.bzl supplies it, exactly as that file
already does for orfs_design().
"""

# Per filegroup target: extensions included in the filegroup.
# config_mk_parser produces these target names from VERILOG_FILES
# wildcard patterns.
_GROUPS = {
    "verilog": ["v", "sv"],
    "include": ["v", "sv", "svh"],
    "lef": ["lef"],
    "lib": ["lib"],
    "gds": ["gds", "gds.gz"],
}

# Extensions exported as individual labels so per-file cross-package
# references resolve. Kept tight on purpose: globbing "*" silently exposes
# LICENSE/.gitignore/etc. as the public API surface. gds/gds.gz are inputs
# in hierarchical flows via ADDITIONAL_GDS.
_EXPORTED_EXTS = [
    "v",
    "sv",
    "svh",
    "tcl",
    "sdc",
    "def",
    "cfg",
    "lef",
    "lib",
    "gds",
    "gds.gz",
]

_EXPORTS_SENTINEL = "_orfs_design_exports_sentinel"

def export_design_files():
    """Publicly export per-file labels for cross-package references.

    config_mk_parser turns $(DESIGN_HOME)/... and $(PLATFORM_DIR)/...
    paths in a config.mk into per-file bazel labels like
    //flow/designs/<plat>/<other>:constraint.sdc. Those labels resolve
    only if the source package calls exports_files() on the individual
    files -- being part of a public filegroup is not sufficient.

    Idempotent: design() and files() both call this, and a BUILD file may
    legitimately call files() more than once (e.g. files("verilog") and
    files("lef") in the same package). A second native.exports_files over
    the same paths is a duplicate-target error, so a sentinel rule
    short-circuits subsequent calls within the same package.

    native.glob() and native.existing_rules() resolve against the calling
    BUILD file's package, not this file's, so moving the DSL between
    modules does not change which files are exported.
    """
    if _EXPORTS_SENTINEL in native.existing_rules():
        return
    exported = native.glob(
        ["*.{}".format(e) for e in _EXPORTED_EXTS],
        allow_empty = True,
    )
    if exported:
        native.exports_files(exported, visibility = ["//visibility:public"])
    native.filegroup(
        name = _EXPORTS_SENTINEL,
        srcs = [],
        visibility = ["//visibility:private"],
    )

def design(
        orfs_design,
        config = "config.mk",
        user_arguments = [],
        user_sources = [],
        local_arguments = [],
        visibility = ["//visibility:public"]):
    """Standard BUILD body for a design package.

    Args:
        orfs_design: the DESIGNS-bound orfs_design() from the generated
            @orfs_designs//:designs.bzl. Passed in rather than loaded
            because DESIGNS is per-consumer.
        config: The config.mk file that drives this design.
        user_arguments: config.mk var names that are project-specific
            (read by the design's own .tcl/.mk, not by ORFS) and should
            bypass the variables.yaml validator.
        user_sources: config.mk var names that are project-specific
            source-typed (path-label) hooks read only by the design's own
            .tcl/.mk; the file is still staged into the sandbox but the
            var name skips variables.yaml validation.
        local_arguments: config.mk var names that are pure make-only
            helpers (used only via $(VAR) expansion within the same
            config.mk, never read by ORFS or by user .tcl/.mk). Dropped
            entirely before orfs_flow() is invoked.
        visibility: visibility of the generated flow targets. Public by
            default: a design package exists to be built, and a consumer
            in another module cannot collect <design>_test into a
            test_suite without it. Command-line targets ignore visibility,
            so this only matters for dependency edges.
    """
    export_design_files()
    orfs_design(
        config = config,
        user_arguments = user_arguments,
        user_sources = user_sources,
        local_arguments = local_arguments,
        visibility = visibility,
    )

def files(group, extra_srcs = None):
    """Named filegroup over conventional extensions.

    Also exports the same files individually so per-file labels (e.g.
    //flow/designs/src/gcd:gcd.v) resolve from sibling packages;
    config_mk_parser emits such labels for $(DESIGN_HOME)/src/<name>/<file>
    references.

    Args:
        group: one of the keys of _GROUPS.
        extra_srcs: additional sources to include beyond the glob.
    """
    if group not in _GROUPS:
        fail("files(): unknown group %r; expected one of %s" % (
            group,
            sorted(_GROUPS.keys()),
        ))
    srcs = native.glob(
        ["*.{}".format(e) for e in _GROUPS[group]],
        allow_empty = True,
    ) + (extra_srcs or [])
    native.filegroup(
        name = group,
        srcs = srcs,
        visibility = ["//visibility:public"],
    )
    export_design_files()

# Exposed for the generated designs.bzl and for tests.
GROUPS = _GROUPS

EXPORTED_EXTS = _EXPORTED_EXTS
