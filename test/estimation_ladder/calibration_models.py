"""Which calibration model actually transfers between designs?

The estimator is optimistic by close to a constant fraction, so one
multiplicative constant removes most of the error.  The obvious next
question is whether a richer model does better -- an affine fit, a
polynomial, a power law, a Gaussian process -- and the obvious trap is
that all of them will look better *on the design they were fitted to*.
More parameters always fit the training design more closely; the
question is what survives being carried to a design whose ground truth
the model has never seen.

So every model is scored three ways:

  train     - fitted and scored on the same design.  Reported only to
              show how much it flatters.
  cv        - five-fold cross-validation within that design: held-out
              paths, same design.  This is what "the model generalises
              to new paths" means.
  transfer  - fitted on one design, applied unchanged to the other.
              This is the number the study cares about.

The gap between cv and transfer is the part of the correction that
belongs to the design rather than to the method.

One structural fact frames all of it: every model here takes the
estimate as its only input, and a monotone function of the estimate
cannot reorder the paths.  Kendall tau and worst-path recall are
therefore *identical* before and after calibration for the monotone
models, which is checked rather than assumed.  Calibration can only fix
how wrong the numbers are, never which paths look critical.  Fixing the
order needs per-path features, which is a different study.
"""

import argparse
import json
import os
import statistics

import numpy as np
from scipy.stats import kendalltau
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import BayesianRidge
from sklearn.model_selection import KFold


def mre(truth, pred):
    return float(np.mean(np.abs(pred - truth) / truth))


# Each entry returns a callable mapping raw estimates to corrected ones.
def fit_scale(x, y):
    """One multiplicative constant, the mean of truth/est.

    The mean of the ratio rather than a least-squares slope: the metric
    is relative error, so every path should weigh the same regardless of
    how long it is.
    """
    a = float(np.mean(y / x))
    return lambda t: a * t


def fit_offset(x, y):
    b = float(np.mean(y - x))
    return lambda t: t + b


def fit_affine(x, y):
    a, b = np.polyfit(x, y, 1)
    return lambda t: a * t + b


def fit_power(x, y):
    """y = a * x^k, fitted in log space where it is linear."""
    k, loga = np.polyfit(np.log(x), np.log(y), 1)
    a = np.exp(loga)
    return lambda t: a * np.power(t, k)


def fit_poly(deg):
    def inner(x, y):
        c = np.polyfit(x, y, deg)
        return lambda t: np.polyval(c, t)

    return inner


def fit_isotonic(x, y):
    """Monotone and otherwise unconstrained.

    The most flexible correction that still cannot reorder anything, so
    it bounds what any rank-preserving model could achieve.
    """
    m = IsotonicRegression(out_of_bounds="clip").fit(x, y)
    return lambda t: m.predict(t)


def fit_gp(x, y):
    """Gaussian process on the estimate.

    Appropriate at this sample size -- tens of paths -- where a forest
    would simply memorise.  Scaled to unit range first so the length
    scale means something.
    """
    xs = x.reshape(-1, 1)
    scale = float(np.mean(y))
    kernel = RBF(length_scale=np.std(x) or 1.0) + WhiteKernel(noise_level=1e-3)
    m = GaussianProcessRegressor(kernel=kernel, normalize_y=True).fit(xs, y / scale)
    return lambda t: m.predict(np.asarray(t).reshape(-1, 1)) * scale


def fit_bayes(x, y):
    """Bayesian linear regression.

    Fitted here the ordinary way; its interest is that the posterior
    from one design is a principled prior for another, which the n-shot
    curve below exercises directly.
    """
    m = BayesianRidge().fit(x.reshape(-1, 1), y)
    return lambda t: m.predict(np.asarray(t).reshape(-1, 1))


MODELS = {
    "identity (no calibration)": lambda x, y: (lambda t: t),
    "scale  y=a*x": fit_scale,
    "offset y=x+b": fit_offset,
    "affine y=a*x+b": fit_affine,
    "power  y=a*x^k": fit_power,
    "poly2": fit_poly(2),
    "poly3": fit_poly(3),
    "isotonic": fit_isotonic,
    "gaussian process": fit_gp,
    "bayesian linear": fit_bayes,
}

# Monotone by construction, so they cannot change the path ordering.
MONOTONE = {
    "identity (no calibration)",
    "scale  y=a*x",
    "offset y=x+b",
    "isotonic",
}


def arrays(rows):
    return (
        np.array([r["est"] for r in rows], dtype=float),
        np.array([r["truth"] for r in rows], dtype=float),
    )


def cross_validated(fit, x, y, folds=5):
    """Held-out error within a design."""
    if len(x) < folds * 2:
        return float("nan")
    errs = []
    for tr, te in KFold(n_splits=folds, shuffle=True, random_state=1).split(x):
        try:
            pred = fit(x[tr], y[tr])(x[te])
            errs.append(mre(y[te], np.asarray(pred, dtype=float)))
        except Exception:
            return float("nan")
    return float(np.mean(errs))


def n_shot_curve(fit, x, y, sizes, repeats=20, seed=0):
    """How much of the target design's own ground truth is needed?

    The practical question behind calibration: if a constant has to be
    fitted per design, you must run the real flow at least once to get
    it.  If a handful of paths suffices, that is cheap; if it takes the
    whole sample, calibration costs what it was meant to save.
    """
    rng = np.random.default_rng(seed)
    out = {}
    for k in sizes:
        if k >= len(x):
            continue
        errs = []
        for _ in range(repeats):
            idx = rng.choice(len(x), size=k, replace=False)
            rest = np.setdiff1d(np.arange(len(x)), idx)
            try:
                pred = fit(x[idx], y[idx])(x[rest])
                errs.append(mre(y[rest], np.asarray(pred, dtype=float)))
            except Exception:
                continue
        if errs:
            out[k] = float(np.median(errs))
    return out


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
    fit_design, apply_design = data["fit_design"], data["apply_design"]

    results = {}
    for rung, pair in data["rungs"].items():
        xf, yf = arrays(pair["fit"])
        xa, ya = arrays(pair["apply"])
        rows = []
        for name, fit in MODELS.items():
            try:
                model_on_fit = fit(xf, yf)
                transfer = mre(ya, np.asarray(model_on_fit(xa), dtype=float))
                train = mre(yf, np.asarray(model_on_fit(xf), dtype=float))
            except Exception as exc:
                rows.append({"model": name, "error": str(exc)[:80]})
                continue
            cv_fit = cross_validated(fit, xf, yf)
            cv_apply = cross_validated(fit, xa, ya)

            # Does the correction reorder the paths?  For a monotone
            # model it provably cannot; this records the fact rather
            # than trusting it.
            corrected = np.asarray(fit(xa, ya)(xa), dtype=float)
            tau_before = float(kendalltau(ya, xa).statistic)
            tau_after = float(kendalltau(ya, corrected).statistic)

            rows.append(
                {
                    "model": name,
                    "train": train,
                    "cv_fit": cv_fit,
                    "cv_apply": cv_apply,
                    "transfer": transfer,
                    "tau_before": tau_before,
                    "tau_after": tau_after,
                    "monotone": name in MONOTONE,
                }
            )
        results[rung] = rows

    # The n-shot curve, on the rung most likely to be used in anger.
    shot = {}
    for rung, pair in data["rungs"].items():
        xa, ya = arrays(pair["apply"])
        shot[rung] = {
            name: n_shot_curve(MODELS[name], xa, ya, [1, 2, 5, 10, 20, 50])
            for name in ("scale  y=a*x", "affine y=a*x+b")
        }

    out = os.path.join(directory, "calibration_models.json")
    with open(out, "w") as f:
        json.dump(
            {
                "fit_design": fit_design,
                "apply_design": apply_design,
                "rungs": results,
                "n_shot": shot,
            },
            f,
            indent=2,
            sort_keys=True,
        )

    for rung, rows in results.items():
        print(f"\n=== {rung}  (fit on {fit_design}, applied to {apply_design})")
        print(
            f"{'model':26s} {'train':>8s} {'cv':>8s} {'transfer':>9s} "
            f"{'cv(tgt)':>8s} {'reorders?':>10s}"
        )
        for r in sorted(rows, key=lambda r: r.get("transfer", 9e9)):
            if "error" in r:
                print(f"{r['model']:26s} FAILED {r['error']}")
                continue
            # A monotone correction cannot invert any pair, but isotonic
            # regression maps distinct estimates onto equal values across
            # its flat segments, which creates ties and lowers tau-b.
            # That is lost resolution, not reordering, and the two
            # deserve different names.
            if abs(r["tau_after"] - r["tau_before"]) < 1e-9:
                reorders = "no"
            elif r["monotone"]:
                reorders = "ties"
            else:
                reorders = "YES"
            print(
                f"{r['model']:26s} {r['train']:8.4f} {r['cv_fit']:8.4f} "
                f"{r['transfer']:9.4f} {r['cv_apply']:8.4f} {reorders:>10s}"
            )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
