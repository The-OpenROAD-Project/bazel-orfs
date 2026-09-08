load("@bazel_orfs_test_designs//:designs.bzl", "DESIGNS", "design")
load("//:rc.bzl", "orfs_correlate_rc", "orfs_write_rc")

# The two lines every ORFS design package has. Visible to the study
# package that drives the campaigns over this design.
design(
    config = "config.mk",
    # Read by this design's own constraint.sdc, not by ORFS, so it
    # bypasses the variables.yaml spell-checker rather than being
    # rejected by it.
    user_arguments = ["WIREBOUND_CLK_PERIOD_PS"],
    visibility = ["//test:__subpackages__"],
)

# ORFS's unit-RC calibration, declared here rather than beside the study
# that reads it: RESULTS_DIR is derived from the declaring package, so a
# run that loads a stage's outputs has to live where those outputs are
# written. See orfs_write_rc's docstring.
#
# This is what the design is for. Fitting a pre-route wire model needs
# detailed route and two extractions, which the designs that most need it
# cannot afford; wirebound reaches final in ~340s while being the only
# asap7 design that puts signal and clock nets on M8/M9 -- and a layer
# with no routed segments contributes nothing to the fit.
orfs_write_rc(
    name = "wirebound_write_rc",
    src = ":wirebound_final",
    arguments = {
        key: value
        for key, value in DESIGNS["asap7/wirebound"]["arguments"].items()
        if key != "WIREBOUND_CLK_PERIOD_PS"
    },
    results_dir = "results/asap7/wirebound/base",
    sources = DESIGNS["asap7/wirebound"]["sources"],
    user_arguments = {
        "WIREBOUND_CLK_PERIOD_PS": DESIGNS["asap7/wirebound"]["arguments"].get(
            "WIREBOUND_CLK_PERIOD_PS",
        ),
    },
    visibility = ["//test:__subpackages__"],
)

# The per-layer R-squared this prints is the number to read first: M9
# carries the fewest segments of any routable layer here, and a badly
# determined coefficient is not a calibration.
orfs_correlate_rc(
    name = "wirebound_correlate_rc",
    segments_rc = [":results/asap7/wirebound/base/6_segments_rc.csv"],
    visibility = ["//test:__subpackages__"],
    # ORFS's fit is a scikit-learn through-origin regression; the pip
    # repository is named by the caller so rc.bzl does not depend on
    # bazel-orfs's dev-only pip.
    deps = [
        # correlateRC.py imports both: scikit-learn for the through-origin
        # regressions, matplotlib for the grt-vs-RCX plots it can emit.
        "@bazel-orfs-dev-pip//matplotlib",
        "@bazel-orfs-dev-pip//scikit_learn",
    ],
)
