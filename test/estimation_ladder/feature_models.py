"""Can anything about an individual path fix the ordering?

Calibration cannot.  Every correction that reads only the estimate is a
monotone function of it, so it moves all the numbers and reorders none
of them -- and the ordering is the part the estimator gets wrong,
especially on the macro design where it barely beats guessing at which
paths are critical.

Reordering requires knowing something about the path itself.  The
physically obvious candidate is how far the path reaches: the error is
wire-related, and endpoints that sit far apart leave more room for the
router to add detour than a local path does.  Alongside it, whether the
path terminates on a macro pin, and the fanout it drives.

So this fits models on (estimate, features) rather than on the estimate
alone, and asks two questions that the calibration study could not:

  does it predict better    - held-out and cross-design error, against
                              the best estimate-only correction;
  does it reorder better    - rank correlation and worst-path recall
                              after correction, against the chance level
                              and against the uncorrected estimate.

The second is the one that matters.  A feature model that improves the
numbers but leaves the ordering alone has bought nothing calibration
had not already.
"""

import argparse
import json
import os

import numpy as np
from scipy.stats import kendalltau
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

FEATURES = ("dist_um", "macro_ends", "fanout")


def mre(truth, pred):
    return float(np.mean(np.abs(pred - truth) / truth))


def matrix(rows, use_features):
    """Design matrix: the estimate, optionally plus path features."""
    cols = [[r["est"] for r in rows]]
    if use_features:
        for f in FEATURES:
            if any(f in r for r in rows):
                cols.append([r.get(f, 0.0) for r in rows])
    return np.array(cols, dtype=float).T


def truths(rows):
    return np.array([r["truth"] for r in rows], dtype=float)


def recall_at_k(truth, pred, k=10):
    n = min(k, len(truth))
    worst_true = set(np.argsort(-truth)[:n].tolist())
    worst_pred = set(np.argsort(-pred)[:n].tolist())
    return len(worst_true & worst_pred) / n


MODELS = {
    "scale (estimate only)": lambda: None,  # handled specially
    "ridge + features": lambda: Ridge(alpha=1.0),
    "gradient boosting + features": lambda: GradientBoostingRegressor(
        random_state=1, n_estimators=200, max_depth=2
    ),
    "random forest + features": lambda: RandomForestRegressor(
        random_state=1, n_estimators=200, min_samples_leaf=4
    ),
}


def fit_predict(name, xtr, ytr, xte):
    if name == "scale (estimate only)":
        a = float(np.mean(ytr / xtr[:, 0]))
        return a * xte[:, 0]
    model = MODELS[name]().fit(xtr, ytr)
    return model.predict(xte)


def cross_validated(name, x, y, folds=5):
    if len(x) < folds * 2:
        return float("nan"), float("nan"), float("nan")
    errs, taus, recs = [], [], []
    for tr, te in KFold(n_splits=folds, shuffle=True, random_state=1).split(x):
        pred = fit_predict(name, x[tr], y[tr], x[te])
        errs.append(mre(y[te], pred))
        if len(te) > 2:
            taus.append(float(kendalltau(y[te], pred).statistic))
    return (
        float(np.mean(errs)),
        float(np.mean(taus)) if taus else float("nan"),
        float("nan"),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paths-json", default=None)
    args = ap.parse_args()

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    directory = os.path.join(ws, "test/estimation_ladder")
    src = args.paths_json or os.path.join(directory, "calibration_paths.json")
    if not os.path.exists(src):
        raise SystemExit(f"not found: {src}; run calibration_transfer first")
    data = json.load(open(src))

    out = {}
    for rung, pair in data["rungs"].items():
        fit_rows, app_rows = pair["fit"], pair["apply"]
        if not any(f in fit_rows[0] for f in FEATURES):
            raise SystemExit(
                "no per-path features in the archive; re-run "
                "calibration_transfer with the feature dump enabled"
            )
        rows = []
        yf, ya = truths(fit_rows), truths(app_rows)
        raw_tau = float(kendalltau(ya, matrix(app_rows, False)[:, 0]).statistic)
        raw_rec = recall_at_k(ya, matrix(app_rows, False)[:, 0])
        for name in MODELS:
            use_f = name != "scale (estimate only)"
            xf, xa = matrix(fit_rows, use_f), matrix(app_rows, use_f)
            if xf.shape[1] != xa.shape[1]:
                continue
            transfer_pred = fit_predict(name, xf, yf, xa)
            cv_err, cv_tau, _ = cross_validated(name, xa, ya)
            rows.append(
                {
                    "model": name,
                    "transfer_err": mre(ya, transfer_pred),
                    "transfer_tau": float(kendalltau(ya, transfer_pred).statistic),
                    "transfer_recall": recall_at_k(ya, transfer_pred),
                    "cv_err": cv_err,
                    "cv_tau": cv_tau,
                }
            )
        out[rung] = {
            "raw_tau": raw_tau,
            "raw_recall": raw_rec,
            "n_paths": len(app_rows),
            "models": rows,
        }

    path = os.path.join(directory, "feature_models.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)

    for rung, res in out.items():
        chance = 10.0 / res["n_paths"]
        print(
            f"\n=== {rung}   uncorrected tau {res['raw_tau']:+.3f}, "
            f"recall {res['raw_recall']:.2f} (chance {chance:.2f})"
        )
        print(
            f"{'model':30s} {'err':>8s} {'tau':>8s} {'recall':>8s} "
            f"{'cv err':>8s} {'cv tau':>8s}"
        )
        for r in sorted(res["models"], key=lambda r: r["transfer_err"]):
            print(
                f"{r['model']:30s} {r['transfer_err']:8.4f} "
                f"{r['transfer_tau']:+8.3f} {r['transfer_recall']:8.2f} "
                f"{r['cv_err']:8.4f} {r['cv_tau']:+8.3f}"
            )
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
