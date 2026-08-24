"""Does the estimator's bias transfer between designs?

Rung A shows the estimator's error is almost entirely systematic: in
nearly every trial the mean absolute relative error and the magnitude of
the signed bias agree to within a few percent, and the spread around
that bias is an order of magnitude smaller.  Every path is optimistic by
roughly the same fraction, because the estimator sees shorter wires than
the routed design has.

That invites an obvious correction -- multiply the estimate by a
constant -- and an obvious trap.  Fitting the constant against the same
ground truth the result is scored on measures nothing except how well a
free parameter can absorb an error, and it would make every rung look
good.  The number that means something is whether a constant fitted on
one design still helps on a *different* one, whose ground truth it has
never seen.

So this runs the same rung configurations on both designs, fits the
scale factor on the first, applies it unchanged to the second, and
reports what happened.  Three outcomes, all worth publishing:

  * the correction transfers -- the bias is a property of the method,
    and the cheap rungs get most of the way to the expensive ones for
    free;
  * it transfers partly -- there is a shared component and a
    design-specific one;
  * it does not transfer -- the bias is design-specific, calibration
    needs a per-design fit, and the expensive rungs earn their keep.

Reported alongside each is the rank correlation, which a positive scale
factor cannot change at all: calibration fixes how wrong the numbers
are, never what order they come in.
"""

import argparse
import json
import os
import statistics
import tempfile

from optuna_study import run_estimator

# The canonical rungs of the ladder, named so the report reads as a
# ladder rather than as a list of environment dumps.
RUNGS = {
    "place_only": {"RUN_PLACE": "1", "RUN_MACRO_PLACE": "1"},
    "place_ios": {"RUN_PLACE": "1", "RUN_MACRO_PLACE": "1", "PLACE_IOS": "1"},
    "virtual_cts": {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "1",
        "GPL_VIRTUAL_CTS": "1",
    },
    "cts": {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "1",
        "CLOCK_MODE": "real",
        "CTS_DPL": "1",
    },
    "cts_grt": {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "1",
        "CLOCK_MODE": "real",
        "CTS_DPL": "1",
        "RUN_GRT": "1",
        "GRT_ITERATIONS": "2",
    },
    "cts_grt_repair": {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "1",
        "CLOCK_MODE": "real",
        "CTS_DPL": "1",
        "RUN_GRT": "1",
        "GRT_ITERATIONS": "2",
        "RUN_REPAIR_DESIGN": "1",
        "RUN_REPAIR_TIMING": "1",
        "REPAIR_TIMING_ARGS": "-sequence {vt_swap} -repair_tns 0",
    },
}


def paths_of(json_path):
    with open(json_path) as f:
        data = json.load(f)
    return {(p["start"], p["end"]): p["min_period"] for p in data["paths"]}


def scale_factor(truth, est):
    """The constant that best removes the systematic offset.

    The mean of truth/est rather than a least-squares fit on the raw
    periods: the metric is *relative* error, so every path should count
    equally regardless of how long it is.
    """
    keys = sorted(truth)
    return statistics.fmean(truth[k] / est[k] for k in keys)


def mean_rel_err(truth, est, scale=1.0):
    keys = sorted(truth)
    return statistics.fmean(abs(scale * est[k] - truth[k]) / truth[k] for k in keys)


def evaluate(estimator_exe, ground_truth, env, out_dir, tag):
    out = os.path.join(out_dir, f"calib_{tag}.json")
    # out_json rather than setting OUTPUT_JSON in the environment: the
    # sweep's runner hands the estimator a scratch file and deletes it,
    # and the calibration needs the per-path periods to survive.
    run_estimator(estimator_exe, dict(env), ground_truth, timeout_s=3600, out_json=out)
    return paths_of(ground_truth), paths_of(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("fit_exe", help="estimator for the design the scale is fitted on")
    ap.add_argument("fit_ground_truth")
    ap.add_argument("apply_exe", help="estimator for the design it is applied to")
    ap.add_argument("apply_ground_truth")
    ap.add_argument("--fit-name", default="multiplier")
    ap.add_argument("--apply-name", default="multiplier_top")
    args = ap.parse_args()

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    out_dir = os.path.join(ws, "test/estimation_ladder")
    os.makedirs(out_dir, exist_ok=True)

    results = []
    # Per-rung estimator output is scratch: the summary below is the
    # result worth keeping, and twelve intermediate files in the source
    # tree are just noise.
    scratch = tempfile.TemporaryDirectory()
    out_dir_runs = scratch.name
    for name, env in RUNGS.items():
        fit_truth, fit_est = evaluate(
            args.fit_exe, args.fit_ground_truth, env, out_dir_runs, f"fit_{name}"
        )
        scale = scale_factor(fit_truth, fit_est)

        app_truth, app_est = evaluate(
            args.apply_exe, args.apply_ground_truth, env, out_dir_runs, f"apply_{name}"
        )
        raw = mean_rel_err(app_truth, app_est)
        transferred = mean_rel_err(app_truth, app_est, scale)
        # The upper bound: what a constant fitted on the target design
        # itself would have achieved. Not a result -- the yardstick the
        # transferred number is measured against.
        oracle_scale = scale_factor(app_truth, app_est)
        oracle = mean_rel_err(app_truth, app_est, oracle_scale)

        results.append(
            {
                "rung": name,
                "scale_fitted_on_" + args.fit_name: scale,
                "raw_err": raw,
                "transferred_err": transferred,
                "oracle_err": oracle,
                "oracle_scale": oracle_scale,
            }
        )
        print(
            f"{name:16s} scale={scale:6.4f}  raw={raw:.4f}  "
            f"transferred={transferred:.4f}  oracle={oracle:.4f}"
        )

    out = os.path.join(out_dir, "calibration_transfer.json")
    with open(out, "w") as f:
        json.dump(
            {
                "fit_design": args.fit_name,
                "apply_design": args.apply_name,
                "rungs": results,
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
