"""Bazel macros for ORFS's unit-RC calibration procedure.

ORFS fits the per-layer resistance and capacitance that pre-route timing
runs on -- the numbers `set_layer_rc` and `set_wire_rc` install in
`flow/platforms/<pdk>/setRC.tcl` -- by regressing routed segment
parasitics against extracted ones. The procedure is documented in
`docs/tutorials/SetRC.md` and implemented by two make targets,
`write_rc` and `correlate_rc`, and it is unreachable from a bazel build:
nothing in bazel-orfs exposes either.

That is worth fixing on its own terms. The tutorial states why the
numbers matter -- "Inaccurate unit RC values can lead to inconsistent
timing results between global route and detailed route" -- and every
pre-route stage, including timing-driven global placement and every
repair budget downstream of it, works from them.

Two things to know before using this.

**It is gated behind the most expensive part of the flow.** `write_rc`
loads `6_final.odb`, reads the RCX SPEF, and then runs a *second* RCX
extraction with merging disabled to get per-segment parasitics. So the
wire model that steers placement can only be calibrated after detailed
route and two extractions -- a loop no large design closes in practice,
which is why a small design that still exercises the upper layers is
useful here.

**A layer with no routed segments is skipped, not estimated.** ORFS's
`fit_layer_models` drops any layer absent from the segment data, so it
gets no fitted value *and contributes nothing to the `set_wire_rc`
blend*, which is a length-weighted mean over the layers that appear. A
design whose `MAX_ROUTING_LAYER` excludes the top of the stack therefore
produces a wire model that has never seen it. Check the per-layer R²
that `correlate_rc` prints before trusting a layer's row.

Power and ground nets are excluded by ORFS (`fetch_segments_rc` keeps
only SIGNAL and CLOCK), so the fit sees signal and clock routing only.
"""

load("@bazel-orfs//:openroad.bzl", "orfs_run")
load("@rules_python//python:defs.bzl", "py_binary")

# The two CSVs `make write_rc` writes into RESULTS_DIR. The nets file
# feeds the plots; the segments file is the only input the fit reads.
_NETS_RC = "6_nets_rc.csv"

_SEGMENTS_RC = "6_segments_rc.csv"

def orfs_write_rc(
        name,
        src,
        arguments = {},
        sources = {},
        results_dir = None,
        tags = ["manual"],
        visibility = None,
        **kwargs):
    """Write the segment and net RC CSVs for a routed, extracted design.

    Wraps ORFS's `do-write_rc`. `src` must be a `final` stage target:
    ORFS's script loads `6_final.odb` and reads `6_final.spef`, so a grt
    or route stage has neither the routed segments nor the extracted
    parasitics it compares against.

    **Declare this in the same package as `src`.** RESULTS_DIR is derived
    from the declaring package, not from the src's, so a target declared
    elsewhere gets a RESULTS_DIR that holds none of the files ORFS's
    script loads -- and the failure reads as `ORD-0007 ... does not
    exist`, which looks like a missing input rather than a
    misconfiguration. Only LOG_DIR follows the src, which makes the
    mistake harder to spot. Do not pass a `variant` either, for the same
    reason: it moves RESULTS_DIR off the directory the final stage wrote.

    `do-write_rc` rather than `write_rc` because bazel is doing the
    dependency checking: the file target decides whether to run, this
    macro's caller has already decided.

    Args:
        name: base name; the CSVs are declared as `<results_dir>/6_*.csv`
        src: the design's `_final` stage target
        arguments: ORFS variables for the run
        sources: source-typed ORFS variables for the run
        results_dir: path prefix for the declared outputs, following the
            ORFS convention `results/<platform>/<design>/<variant>`.
            Passed explicitly because bazel must declare outputs at
            analysis time, before those values are known here.
        tags: forwarded; manual by default, since this needs a full flow
        visibility: forwarded
        **kwargs: forwarded to orfs_run
    """
    if results_dir == None:
        fail("orfs_write_rc() requires results_dir: the CSVs are written " +
             "into RESULTS_DIR by ORFS and bazel has to declare them as " +
             "outputs before that path can be derived")

    orfs_run(
        name = name,
        src = src,
        outs = [
            "{}/{}".format(results_dir, _NETS_RC),
            "{}/{}".format(results_dir, _SEGMENTS_RC),
        ],
        arguments = arguments,
        cmd = "do-write_rc",
        # orfs_run requires a script even for a cmd that does not read
        # one; ORFS's own write_rc.tcl is what do-write_rc runs.
        script = "@orfs//flow/util:write_rc.tcl",
        # ORFS's write_rc.tcl and its helper, declared so they exist in
        # the sandbox. Bazel stages an external repository's files at
        # their repo-relative path, which is exactly where UTILS_DIR
        # points, so the wrapper can source them the way ORFS does
        # rather than by a path this file would have to construct. The
        # variable itself is never read.
        sources = sources,
        user_sources = {
            "ORFS_WRITE_RC_SRCS": [
                "@orfs//flow/util:write_rc.tcl",
                "@orfs//flow/util:write_rc_helper.tcl",
            ],
        },
        tags = tags,
        visibility = visibility,
        **kwargs
    )

def orfs_correlate_rc(
        name,
        segments_rc,
        deps,
        cap_unit = "ff",
        res_unit = "kohm",
        tags = ["manual"],
        visibility = None):
    """Fit per-layer RC and the wire-RC blend from segment CSVs.

    Runs ORFS's `correlateRC.py` -- deliberately ORFS's script rather
    than a reimplementation, because the point of a fitted value is that
    it was produced by the same procedure as the one it is compared
    against. Reimplementing the regression would make every number a new
    claim rather than a measurement.

    Prints a `setRC.tcl` body plus the per-layer R² for each fit. Several
    segment CSVs may be passed at once, which is how a platform-wide fit
    is made from more than one design; note that this averages the
    designs' layer *usage* into one blend, so adding a design with
    unusual layer usage moves the blend for everyone.

    Args:
        name: target name
        segments_rc: one or more `6_segments_rc.csv` labels
        deps: Python dependencies for the fit -- ORFS's correlateRC.py
            imports scikit-learn and numpy. Required rather than
            defaulted, because the label of a pip repository belongs to
            the consumer: naming bazel-orfs's own here would break every
            downstream module, which is what //:public_surface checks
            for.
        cap_unit: capacitance unit, ff or pf. ff matches what the asap7
            platform file carries.
        res_unit: resistance unit, ohm or kohm
        tags: forwarded; manual by default
        visibility: forwarded
    """

    # Copied into this package rather than referenced in place: the
    # runfiles path of an external repository embeds its mangled
    # canonical name, which is not something a BUILD file should spell.
    #
    # Copied into a per-target subdirectory, and under their ORIGINAL
    # names, because correlateRC.py does `from correlateRCHelper import
    # ...` -- a bare module import. Prefixing the file names to keep them
    # unique in the package renames the module and the import fails; the
    # subdirectory gives uniqueness without touching the names. It is
    # suffixed `_srcs` rather than named after the target, because a
    # directory sharing the py_binary's own name collides with its
    # executable output.
    native.genrule(
        name = name + "_scripts",
        srcs = [
            "@orfs//flow/util:correlateRC.py",
            "@orfs//flow/util:correlateRCHelper.py",
        ],
        outs = [
            name + "_srcs/correlateRC.py",
            name + "_srcs/correlateRCHelper.py",
        ],
        cmd = "cp $(location @orfs//flow/util:correlateRC.py) $(location " +
              name + "_srcs/correlateRC.py) && cp $(location " +
              "@orfs//flow/util:correlateRCHelper.py) $(location " +
              name + "_srcs/correlateRCHelper.py)",
        tags = tags,
    )

    py_binary(
        name = name,
        srcs = [
            name + "_srcs/correlateRC.py",
            name + "_srcs/correlateRCHelper.py",
        ],
        args = [
            "-cap_unit",
            cap_unit,
            "-res_unit",
            res_unit,
            "-segments_rc_file",
        ] + ["$(rootpath {})".format(label) for label in segments_rc],
        data = segments_rc,
        imports = [name + "_srcs"],
        main = name + "_srcs/correlateRC.py",
        tags = tags,
        visibility = visibility,
        deps = deps,
    )
