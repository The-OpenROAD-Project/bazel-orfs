#!/usr/bin/env python3
"""Score the forecasters against recorded runs.

Every prefix of every recorded series is a question the forecaster
could have been asked at the time, and the rest of the series is the
answer. So a handful of runs yields a lot of evaluation points.

Two regimes, scored separately, because they have different customers
and can have different verdicts:

  cold   nothing known about this design. What ORFS would ship as a
         default. Scored leave-one-design-out.
  warm   this design has been run before. What a DSE sweep gives you
         for free. Scored leave-one-run-out, and capped at the amount
         of history a real user would actually have.

The headline number is not ETA error, it is *decision accuracy*: given
a budget, does the forecast correctly say whether this run will make
it? That is the decision an anti-futility setting would act on, and a
forecaster can be badly wrong about the ETA while still being reliably
right about the verdict -- or the reverse.
"""

import argparse
import os
import json
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from types import SimpleNamespace

import forecast

# Checkpoints are absolute wall-clock moments, not fractions of the
# run's duration. Fractions leak the answer: asked at "50% of the true
# total", the remaining time is by construction 1.0x the time already
# spent, so a rule that predicts exactly that scores 6% median error
# while knowing nothing at all. An earlier version of this harness made
# that mistake, and the 6% looked like a result.
#
# A forecaster in the field is asked at a moment and has to say how much
# longer from here.
CHECKPOINTS_S = (5.0, 15.0, 30.0, 60.0)

# Budgets are absolute for the same reason: it is what a DSE sweep
# actually sets -- "no more than N seconds per run".
BUDGETS_S = (30.0, 60.0, 120.0, 300.0)


def load(path):
    series = []
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            pts = [SimpleNamespace(**p) for p in d["points"]]
            d["points"] = pts
            series.append(SimpleNamespace(**d))
    return series


def usable(s):
    """A series that can be both asked and answered."""
    stamped = [p for p in s.points if p.t is not None]
    return (
        len(s.points) >= 8
        and len(stamped) >= 8
        and s.terminated
        and forecast.elapsed(s.points) is not None
        and forecast.elapsed(s.points) > 0
    )


def checkpoint_index(s, at_s):
    """The last point at or before `at_s` seconds into the run.

    None when the run is already over by then, or has printed too little
    to say anything: a forecast is only wanted from a run still going.
    """
    pts = s.points
    t0 = pts[0].t
    if pts[-1].t - t0 <= at_s:
        return None
    idx = None
    for i, p in enumerate(pts):
        if p.t is not None and p.t - t0 <= at_s:
            idx = i
    if idx is None or idx < 3:
        return None
    return idx


def evaluate(series, warm_history):
    """ETA accuracy, scored only where an ETA is even well-posed."""
    rows = {}
    for s in series:
        if not usable(s) or not s.converged:
            continue
        for frac in CHECKPOINTS_S:
            k = checkpoint_index(s, frac)
            if k is None:
                continue
            prefix = s.points[: k + 1]
            truth = forecast.truth_remaining(s, k)
            if truth is None:
                continue

            preds = {
                "naive": forecast.naive(prefix, s.target),
                "parametric": forecast.parametric(prefix, s.target),
            }
            hist = [
                h
                for h in warm_history.get(key_of(s), [])
                if not same_run(h, s)
            ]
            if hist:
                preds["library"] = forecast.library(prefix, s.target, hist)

            for name, pred in preds.items():
                row = rows.setdefault(
                    (name, frac),
                    {"n": 0, "declined": 0, "ape": [], "dec": [], "base": []},
                )
                row["n"] += 1
                if pred is None:
                    row["declined"] += 1
                    continue
                if truth > 0:
                    row["ape"].append(abs(pred - truth) / truth)
                spent = s.points[k].t - s.points[0].t
                for budget in BUDGETS_S:
                    left = budget - spent
                    row["dec"].append((pred <= left) == (truth <= left))
                    # What "always say it fits" would score. Without this
                    # the decision column flatters itself: most runs here
                    # are short against most budgets, so the majority
                    # answer is right most of the time.
                    row["base"].append(truth <= left)
    return rows


def futility(series):
    """The decision an anti-futility setting would actually make.

    Watching a grind at some fraction of the way in, will it reach its
    target at all? Ground truth is whether the run converged. The
    predictor is deliberately crude -- a forecaster that declines, or
    that puts the crossing beyond a generous multiple of the time
    already spent, is read as "this will not converge" -- because the
    decision is binary and a crude rule that is right is worth more
    than a precise one that is wrong.

    Reported as a confusion matrix rather than one accuracy number: the
    two mistakes have very different costs. Calling a converging run
    futile throws away a result that was about to land; missing a futile
    run just leaves the default grind in place, which is what happens
    today anyway.
    """
    out = {}
    for frac in CHECKPOINTS_S:
        for name, fn in (
            ("naive", forecast.naive),
            ("parametric", forecast.parametric),
        ):
            tp = fp = tn = fn_ = 0
            for s in series:
                if not usable(s):
                    continue
                k = checkpoint_index(s, frac)
                if k is None:
                    continue
                pred = fn(s.points[: k + 1], s.target)
                spent = s.points[k].t - s.points[0].t
                # "Futile" = no crossing predicted, or one so far out
                # that no realistic budget covers it.
                says_futile = pred is None or pred > 4 * max(spent, 1e-9)
                really_futile = not s.converged
                if says_futile and really_futile:
                    tp += 1
                elif says_futile and not really_futile:
                    fp += 1
                elif not says_futile and really_futile:
                    fn_ += 1
                else:
                    tn += 1
            out[(name, frac)] = (tp, fp, tn, fn_)
    return out


def key_of(s):
    """What counts as 'the same grind, seen before'."""
    return (s.design.split("/")[0], s.stage, s.kind)


def same_run(a, b):
    """Two series from the same log are the same run, not history.

    A stage can print the same table twice -- global placement calls
    rebuffer once per timing-driven interruption -- and those two curves
    are near-identical by construction. Letting one predict the other
    measures nothing about forecasting a *future* run, which is the only
    thing the warm regime claims. Excluded, even though excluding it
    deletes the best-looking row in the table.
    """
    return a.log == b.log


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus", help="JSONL from collect.py")
    args = ap.parse_args(argv)

    series = load(args.corpus)
    hist = {}
    for s in series:
        if usable(s):
            hist.setdefault(key_of(s), []).append(s)

    n_usable = sum(1 for s in series if usable(s))
    print("{} series, {} usable (stamped, terminated, >=8 points)".format(len(series), n_usable))
    if not n_usable:
        print("nothing to score")
        return 0

    conv = [s for s in series if usable(s) and s.converged]
    gave = [s for s in series if usable(s) and not s.converged]
    print("  {} converged, {} gave up short of the target".format(len(conv), len(gave)))

    rows = evaluate(series, hist)
    print()
    print("ETA accuracy, converged runs only (an ETA is ill-posed otherwise)")
    print("{:12s} {:>5s} {:>5s} {:>9s} {:>10s} {:>10s}".format(
        "forecaster", "at", "n", "declined", "median APE", "decision", "base"))
    print("-" * 60)
    for (name, frac), r in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        ape = "{:.0%}".format(statistics.median(r["ape"])) if r["ape"] else "-"
        dec = "{:.0%}".format(sum(r["dec"]) / len(r["dec"])) if r["dec"] else "-"
        if r["base"]:
            share = sum(r["base"]) / len(r["base"])
            base = "{:.0%}".format(max(share, 1 - share))
        else:
            base = "-"
        print("{:12s} {:>4.0f}s {:>6d} {:>9d} {:>10s} {:>10s} {:>6s}".format(
            name, frac, r["n"], r["declined"], ape, dec, base))

    print()
    print("Futility detection: will this run reach its target at all?")
    print("(prevalence = what 'always say futile' would score for precision)")
    print("{:12s} {:>5s} {:>4s} {:>4s} {:>4s} {:>4s} {:>7s} {:>7s}".format(
        "rule", "at", "TP", "FP", "TN", "FN", "recall", "precis", "preval"))
    print("-" * 56)
    for (name, frac), (tp, fp, tn, fn_) in sorted(
        futility(series).items(), key=lambda kv: (kv[0][0], kv[0][1])
    ):
        rec = "{:.0%}".format(tp / (tp + fn_)) if (tp + fn_) else "-"
        pre = "{:.0%}".format(tp / (tp + fp)) if (tp + fp) else "-"
        total = tp + fp + tn + fn_
        prv = "{:.0%}".format((tp + fn_) / total) if total else "-"
        print("{:12s} {:>4.0f}s {:>4d} {:>4d} {:>4d} {:>4d} {:>7s} {:>7s} {:>7s}".format(
            name, frac, tp, fp, tn, fn_, rec, pre, prv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
