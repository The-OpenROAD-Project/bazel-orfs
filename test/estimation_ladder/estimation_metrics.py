"""Accuracy metrics for the estimation ladder.

Mean relative error alone cannot distinguish an estimator that is
systematically optimistic from one that is merely noisy, and only the
first of those is correctable by calibration.  It also says nothing
about whether the near-critical paths come out in the right *order*,
which is the question a designer iterating on RTL actually asks.  So the
study reports a decomposition:

  mean_rel_err  - kept for continuity with earlier results
  bias / spread - the mean and standard deviation of the signed relative
                  error.  A large bias with a small spread is a
                  calibration constant waiting to be fitted; a small bias
                  with a large spread is not.
  kendall_tau   - rank correlation over the sampled paths
  spearman_rho  - rank correlation, tie-tolerant
  worst_recall  - of the k truly worst paths, how many the estimator
                  also ranks in its worst k
"""

import json
import statistics

from scipy.stats import kendalltau, spearmanr


def worst_recall(truth, est, k=10):
    """Fraction of the k worst true paths the estimator also ranks in its
    own worst k.  A larger min_period is worse."""
    keys = list(truth)
    n = min(k, len(keys))
    if n == 0:
        return float("nan")
    truth_worst = set(sorted(keys, key=lambda p: -truth[p])[:n])
    est_worst = set(sorted(keys, key=lambda p: -est[p])[:n])
    return len(truth_worst & est_worst) / n


def load_paths(path_json):
    with open(path_json, "r") as f:
        data = json.load(f)
    return data, {(p["start"], p["end"]): p["min_period"] for p in data["paths"]}


def compute_metrics(truth_json, est_json):
    """Return (metrics dict, raw estimator JSON).

    A path the estimator could not measure is an error, not a fallback:
    silently dropping it would let a configuration look accurate by
    reporting only the paths it happened to find.
    """
    _, truth_paths = load_paths(truth_json)
    est, est_paths = load_paths(est_json)

    if set(truth_paths) != set(est_paths):
        raise ValueError(
            "Estimator path set differs from ground truth: "
            f"missing {set(truth_paths) - set(est_paths)}, "
            f"extra {set(est_paths) - set(truth_paths)}"
        )

    keys = sorted(truth_paths)
    rel = [(est_paths[k] - truth_paths[k]) / truth_paths[k] for k in keys]

    truth_vals = [truth_paths[k] for k in keys]
    est_vals = [est_paths[k] for k in keys]

    return {
        "mean_rel_err": sum(abs(r) for r in rel) / len(rel),
        "bias": statistics.fmean(rel),
        "spread": statistics.pstdev(rel) if len(rel) > 1 else 0.0,
        "kendall_tau": float(kendalltau(truth_vals, est_vals).statistic),
        "spearman_rho": float(spearmanr(truth_vals, est_vals).statistic),
        "worst_recall": worst_recall(truth_paths, est_paths, k=10),
        "runtime_s": est.get("runtime_s"),
        "phases": est.get("phases", {}),
    }, est
