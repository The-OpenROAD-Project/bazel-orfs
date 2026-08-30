"""Did this change help? A quantified, actionable verdict for a PR.

The point of this file is a number a developer can move and plot: "I
moved the KPI by x points in this PR". Everything else in the study
exists to make that number honest.

## Why it is not just a fast flow run

There is no fast ground truth here, and there is no slow one either. A
single exact global route is one draw from a distribution whose spread on
multiplier_top is ~25% of the achieved period, so a verdict built on one
run of anything -- flow or estimator -- is a coin toss wearing a decimal
point. Both arms are therefore ensembles, and the verdict is a statement
about distributions.

## The KPI

Two numbers, because "how much" and "how sure" are different questions:

    shift    the Hodges-Lehmann estimate -- the median of all pairwise
             differences between the change's ensemble and the base's.
             The rank-based analogue of a mean difference, reported in
             the design's own time unit and as a percentage.

    points   100 * (2 * P(change beats base) - 1), so -100..+100 with 0
             meaning no change. This is the Mann-Whitney statistic
             rescaled, and it is what "I moved it +18 points" refers to.

Both are rank-based on purpose. The measured facts about this flow --
25% spread, no correlation between the estimator's perturbation response
and the flow's, wildly non-normal and non-monotone responses -- violate
what a mean-and-t-interval assumes. Ranks assume none of it. It also
makes the estimator's job the weaker one it can actually do: not
predicting the flow's number, but ordering two distributions the way the
flow's own distribution is ordered.

## The line that keeps it a measurement rather than an opinion

Every verdict carries the difference this ensemble could actually
resolve. A KPI without it is a superstition generator: on a design with a
25% noise floor it will hand someone a "win" every other PR, and the
first time it contradicts a developer's own eyes it is dead. So:

    KPI  +2.1 points  (resolvable at k=8: +-9.4)  -> below the floor

is a useful answer, and an actionable one -- raise k, or accept that a
change this size is not measurable here.

## Precision is not accuracy, and the gate must not confuse them

The bootstrap interval says how repeatable the ensemble is. It does not
say how right it is, and measurement shows the gap is real: validating
against flow ensembles on multiplier, the estimator reported a load8
shift of -0.10% [-0.19, +0.04] where the truth was +0.45%. Tight, and
wrong. More k narrows that interval without moving it toward truth.

So a verdict needs the effect to clear TWO bars: its own interval must
exclude no-change, and the shift must exceed a validated accuracy floor
measured against real flow ensembles. Quoting the bootstrap alone would
advertise a precision the estimator cannot back, which is exactly the
failure that kills a KPI's credibility the first time someone checks it
by hand.

ACCURACY_FLOOR_PCT below is the multiplier figure. It is design-specific
and must be re-measured per design with method_validation before this
gate is trusted anywhere else.

## Precision is not accuracy, and the gate must not confuse them

The bootstrap interval says how repeatable the ensemble is. It does not
say how right it is, and measurement shows the gap is real: validated
against flow ensembles on multiplier, the estimator reported a load8
shift of -0.10% [-0.19, +0.04] where the truth was +0.45%. Tight, and
wrong. More k narrows that interval without moving it toward truth.

So a verdict must clear TWO bars: its own interval must exclude
no-change, and the shift must exceed a validated accuracy floor measured
against real flow ensembles. Quoting the bootstrap alone advertises a
precision the estimator cannot back, which is the failure that kills a
KPI the first time someone checks it by hand.

ACCURACY_FLOOR_PCT is the multiplier figure and is design-specific.
Re-measure it with method_validation before trusting this gate elsewhere.

## What the gate does NOT do

It does not re-run the flow, and it does not claim to predict it. What
licenses it is a separate, one-time validation that the estimator's
ordering agrees with the flow's ordering (see the wide_truth ensembles on
multiplier, where the flow is cheap enough to ensemble). Until that has
been run for a given design, this gate is uncalibrated and should not be
shown to anyone.
"""

import argparse
import json
import os
import random
import statistics

from optuna_study import run_estimator_pool

# Perturbations are core-area nudges in whole sites: semantically neutral,
# site-aligned so initialize_floorplan has nothing to snap, and applied
# identically to both arms so the comparison is blocked on them.
#
# The set is fixed and recorded rather than drawn per run. Re-running
# until green is best-of-k selection bias wearing a KPI's clothes, and a
# recorded set makes that visible.
# The smallest shift the estimator was measured to get the DIRECTION of
# right, as a percentage of the achieved period.
#
# From method_validation on multiplier: at a true +0.45% the estimator
# reported -0.10%, wrong in sign, while at a true +9.43% it agreed. So
# the honest floor sits above 0.45% and below 9.43%; 1.0% is the
# conservative round number in that gap. Design-specific -- re-measure
# before using this gate on anything else.
ACCURACY_FLOOR_PCT = 1.0


def perturbations(k):
    """k nudges, spread symmetrically around zero and excluding it.

    Zero is excluded because it is the one perturbation both arms would
    share exactly, which contributes no information about spread.
    """
    out = []
    step = 1
    while len(out) < k:
        out.append(step)
        if len(out) < k:
            out.append(-step)
        step += 1
    return sorted(out)


def hodges_lehmann(base, change):
    """Median of all pairwise differences -- the rank-based effect size.

    Pairs with the Mann-Whitney statistic below: one says how much, the
    other how sure, and they are consistent with each other because both
    are built on the same ordering.
    """
    diffs = [c - b for b in base for c in change]
    return statistics.median(diffs)


def prob_better(base, change):
    wins = sum(1.0 if c < b else (0.5 if c == b else 0.0) for b in base for c in change)
    return wins / (len(base) * len(change))


def bootstrap(base, change, rng, resamples=2000):
    """Intervals for both statistics, by resampling the ensembles.

    The uncertainty that matters is having only k observations of each
    distribution, so that is what is resampled.
    """
    shifts, ps = [], []
    for _ in range(resamples):
        b = [rng.choice(base) for _ in base]
        c = [rng.choice(change) for _ in change]
        shifts.append(hodges_lehmann(b, c))
        ps.append(prob_better(b, c))
    shifts.sort()
    ps.sort()
    lo = int(0.025 * resamples)
    hi = int(0.975 * resamples) - 1
    return (shifts[lo], shifts[hi]), (ps[lo], ps[hi])


def achieved(path):
    with open(path, "r") as f:
        return max(p["min_period"] for p in json.load(f)["paths"])


def ensemble(exe, truth, rung, eps, tag, keep, jobs=None):
    envs = {f"{tag}_e{e}": dict(rung, CORE_AREA_EPS_SITES=str(e)) for e in eps}
    got = run_estimator_pool(exe, envs, truth, keep_results_dir=keep, jobs=jobs)
    out = []
    for cid in envs:
        if got.get(cid) is not None:
            out.append(achieved(os.path.join(keep, f"{cid}.json")))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base_exe", help="estimator for the merge-base")
    ap.add_argument("change_exe", help="estimator for the PR")
    ap.add_argument("truth_json", help="the sampled path list to measure")
    ap.add_argument("-k", type=int, default=8, help="ensemble size per arm")
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument(
        "--accuracy-floor-pct",
        type=float,
        default=ACCURACY_FLOOR_PCT,
        help="smallest shift the estimator is known to get RIGHT, as a "
        "percentage of the achieved period; measure it with "
        "method_validation on the design in question",
    )
    ap.add_argument(
        "--regression-points",
        type=float,
        default=-20.0,
        help="fail only if the KPI is below this AND the interval excludes 0",
    )
    args = ap.parse_args()

    rng = random.Random(0)
    eps = perturbations(args.k)
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    keep = os.path.join(ws, "tmp", "ci_gate")

    # Every gating knob explicit, zeros included: an omitted knob means
    # "whatever ORFS defaults to", and GPL_TIMING_DRIVEN and
    # GPL_ROUTABILITY_DRIVEN are real ORFS variables defaulted to 1.
    # Timing-driven placement is off because it roughly doubled the spread
    # on both designs measured while detecting strictly fewer real changes.
    rung = {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "1",
        "PLACE_IOS": "0",
        "GPL_TIMING_DRIVEN": "0",
        "GPL_ROUTABILITY_DRIVEN": "0",
        "GPL_VIRTUAL_CTS": "0",
        "CLOCK_MODE": "none",
        "RUN_REPAIR_DESIGN": "0",
        "RUN_GRT": "0",
        "RUN_REPAIR_TIMING": "0",
    }

    print(f"perturbations (fixed, recorded): {eps}")
    print("base arm:")
    base = ensemble(args.base_exe, args.truth_json, rung, eps, "base", keep, args.jobs)
    print("change arm:")
    change = ensemble(
        args.change_exe, args.truth_json, rung, eps, "change", keep, args.jobs
    )

    if len(base) < 3 or len(change) < 3:
        raise SystemExit(
            f"too few members survived (base {len(base)}, change {len(change)});"
            " no verdict"
        )

    shift = hodges_lehmann(base, change)
    p = prob_better(base, change)
    (slo, shi), (plo, phi) = bootstrap(base, change, rng)
    base_mid = statistics.median(base)
    points = 100.0 * (2.0 * p - 1.0)
    points_lo = 100.0 * (2.0 * plo - 1.0)
    points_hi = 100.0 * (2.0 * phi - 1.0)
    # What this ensemble could have resolved: the half-width of the
    # interval, in the same points as the KPI.
    resolvable = (points_hi - points_lo) / 2.0
    shift_pct = 100.0 * shift / base_mid
    # Two bars, not one: repeatable AND larger than what the estimator is
    # known to get right. The bootstrap alone measures only the first.
    repeatable = not (plo <= 0.5 <= phi)
    above_accuracy = abs(shift_pct) >= args.accuracy_floor_pct
    conclusive = repeatable and above_accuracy

    print("\n" + "=" * 62)
    print(
        f"  KPI  {points:+.1f} points   (resolvable at k={args.k}: +-{resolvable:.1f})"
    )
    print(
        f"       shift {shift:+.3f} ({100.0 * shift / base_mid:+.2f}%)"
        f"  95% CI [{slo:+.3f}, {shi:+.3f}]"
    )
    print(f"       P(change beats base) = {p:.3f} [{plo:.3f}, {phi:.3f}]")
    print(
        f"       repeatable: {'yes' if repeatable else 'no'}"
        f"   above validated accuracy floor"
        f" ({args.accuracy_floor_pct:.2f}%): {'yes' if above_accuracy else 'no'}"
    )
    if not conclusive:
        print("\n  BELOW THE FLOOR -- no verdict.")
        if not repeatable:
            print(f"  This ensemble resolves about {resolvable:.0f} points and the")
            print("  change moved less. Raise k to resolve an effect this size.")
        if not above_accuracy:
            print(
                f"  The shift ({shift_pct:+.2f}%) is under the"
                f" {args.accuracy_floor_pct:.2f}% this estimator is known to get"
            )
            print(
                "  right. More ensemble will not fix that -- it is accuracy,"
                " not precision."
            )
    elif points > 0:
        print("\n  IMPROVED -- the interval excludes no-change.")
    else:
        print("\n  REGRESSED -- the interval excludes no-change.")
    print("=" * 62)

    report = {
        "k": args.k,
        "perturbations": eps,
        "kpi_points": points,
        "kpi_points_ci": [points_lo, points_hi],
        "resolvable_points": resolvable,
        "shift": shift,
        "shift_pct": shift_pct,
        "shift_ci": [slo, shi],
        "prob_better": p,
        "prob_better_ci": [plo, phi],
        "conclusive": conclusive,
        "repeatable": repeatable,
        "above_accuracy_floor": above_accuracy,
        "accuracy_floor_pct": args.accuracy_floor_pct,
        "base_periods": base,
        "change_periods": change,
        "rung": rung,
    }
    out = os.path.join(ws, "test/estimation_ladder", "ci_gate_verdict.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(f"wrote {out}")

    # Non-zero only on a conclusive regression past the threshold. An
    # inconclusive result is not a failure -- it is a statement that the
    # question was not answerable at this ensemble size, and failing on it
    # would teach people to ignore the gate.
    if conclusive and points < args.regression_points:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
