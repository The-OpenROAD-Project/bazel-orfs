"""Does the bias cancel when you compare two variants?

Everything measured so far is absolute error, and absolute error is not
the question an engineer iterating on RTL asks.  They ask whether the
change they just made helped, and by how much.  Both estimates are
optimistic; if they are optimistic by a similar amount then the
*difference* between them is right even though neither number is, and
the estimator is far more useful than its absolute accuracy suggests.

If the bias does not cancel -- if it varies enough between two nearby
designs to swamp the difference being measured -- then the estimator
cannot answer the question it is most likely to be asked, and that is
worth knowing before anyone relies on it.

Three things are reported:

  ranking      - does the estimator put the variants in the right
                 order?  This is the weakest useful claim: "B is faster
                 than A" without saying by how much.
  delta error  - how wrong is the predicted difference, against the
                 true difference.  Compared with how wrong the absolute
                 numbers are, since the whole hypothesis is that this is
                 smaller.
  sign         - how often the estimator gets the direction of a change
                 right.  Getting this wrong is the failure that actually
                 costs someone a day.
"""

import argparse
import itertools
import json
import os
import statistics

from scipy.stats import kendalltau

from estimation_metrics import load_paths
from optuna_study import run_estimator

# The rung to compare with. Cheap enough to be the one someone would
# really put in an iteration loop.
RUNG = {
    "RUN_PLACE": "1",
    "RUN_MACRO_PLACE": "1",
    "RUN_GRT": "1",
    "GRT_ITERATIONS": "2",
}


def critical_period(path_map):
    """A design's achieved period is its worst sampled path."""
    return max(path_map.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--variant",
        action="append",
        required=True,
        metavar="NAME=ESTIMATOR=GROUND_TRUTH",
        help="one per design variant",
    )
    ap.add_argument("--wire-rc-layer", default=None)
    args = ap.parse_args()

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    out_dir = os.path.join(ws, "test/estimation_ladder")

    rows = []
    for spec in args.variant:
        name, exe, truth = spec.split("=", 2)
        env = dict(RUNG)
        if args.wire_rc_layer:
            env["WIRE_RC_LAYER_OVERRIDE"] = args.wire_rc_layer
        out_json = os.path.join(out_dir, f"ab_{name}_est.json")
        run_estimator(exe, env, truth, timeout_s=3600, out_json=out_json)
        _, est_paths = load_paths(out_json)
        _, true_paths = load_paths(truth)
        os.remove(out_json)
        rows.append(
            {
                "variant": name,
                "true": critical_period(true_paths),
                "est": critical_period(est_paths),
                "n_paths": len(true_paths),
            }
        )
        r = rows[-1]
        r["abs_err"] = abs(r["est"] - r["true"]) / r["true"]
        print(
            f"{name:>8s}  true {r['true']:8.1f}  est {r['est']:8.1f}  "
            f"abs err {r['abs_err']:.1%}"
        )

    if len(rows) < 2:
        raise SystemExit("need at least two variants")

    # Ranking: does it order the variants correctly at all?
    tau = float(
        kendalltau([r["true"] for r in rows], [r["est"] for r in rows]).statistic
    )

    # Every pair, since with a handful of variants the pairwise view is
    # the whole picture rather than a sample of it.
    pairs = []
    for a, b in itertools.combinations(rows, 2):
        true_d = b["true"] - a["true"]
        est_d = b["est"] - a["est"]
        pairs.append(
            {
                "pair": f"{a['variant']} -> {b['variant']}",
                "true_delta": true_d,
                "est_delta": est_d,
                # Relative to the true difference: predicting a 30ps gap
                # as 20ps is a third wrong, however small both are.
                "delta_err": abs(est_d - true_d) / abs(true_d) if true_d else None,
                "sign_ok": (true_d > 0) == (est_d > 0) if true_d else None,
            }
        )

    mean_abs = statistics.fmean(r["abs_err"] for r in rows)
    scored = [p for p in pairs if p["delta_err"] is not None]
    mean_delta = statistics.fmean(p["delta_err"] for p in scored) if scored else None
    sign_ok = sum(1 for p in scored if p["sign_ok"])

    print(f"\nvariant ranking: kendall tau {tau:+.3f}")
    print(f"absolute error, mean over variants: {mean_abs:.1%}")
    if mean_delta is not None:
        print(f"delta error, mean over pairs:       {mean_delta:.1%}")
        print(f"direction correct: {sign_ok}/{len(scored)} pairs")
        verdict = (
            "the bias largely cancels -- the difference is better than the numbers"
            if mean_delta < mean_abs
            else "the bias does NOT cancel -- the difference is no better than the "
            "numbers, and may be worse"
        )
        print(f"\n{verdict}")

    print(f"\n{'pair':>22s} {'true delta':>11s} {'est delta':>10s} {'err':>8s} sign")
    for p in pairs:
        de = f"{p['delta_err']:.1%}" if p["delta_err"] is not None else "n/a"
        print(
            f"{p['pair']:>22s} {p['true_delta']:11.1f} {p['est_delta']:10.1f} "
            f"{de:>8s} {'ok' if p['sign_ok'] else 'WRONG'}"
        )

    path = os.path.join(out_dir, "ab_compare.json")
    with open(path, "w") as f:
        json.dump(
            {
                "rung": RUNG,
                "wire_rc_layer": args.wire_rc_layer,
                "variants": rows,
                "pairs": pairs,
                "variant_tau": tau,
                "mean_abs_err": mean_abs,
                "mean_delta_err": mean_delta,
                "sign_correct": sign_ok,
                "pairs_scored": len(scored),
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
