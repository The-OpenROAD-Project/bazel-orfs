"""Is the change good? -- asked of distributions, not of a single run.

There is no fast ground truth here, and more importantly there is no
ground truth. A single exact global route is one draw from a distribution
whose spread on this design is ~25% of the achieved period, so
approximating it faithfully means approximating noise. The question "is
my change good" is a statement about the DISTRIBUTION of achievable
outcomes, and which statement depends on how the design actually ships:

    E[Q]          better on average
    min over k    better at the operating point, if you run the flow a
                  few times and keep the best -- which with a placer this
                  chaotic is what anyone would really do
    P(Q < target) more likely to close timing

They can disagree: a change that raises the mean while widening the
spread improves best-of-k and worsens the average.

So the headline statistic here is rank-based and assumption-free,

    P(Q_change < Q_base)

the chance a random draw from the change beats a random draw from the
base. It needs no pairing, no normality and no correlation between the
estimator and the flow -- all three of which this design violates. 0.5 is
indistinguishable. It also makes the estimator's job the weaker one it
should be: not predicting the flow's number, just ordering the two
distributions the way the flow's own distribution is ordered.

Does more ensemble buy resolution, or is the spread a bias?

The pre-flight found that on `multiplier_top` a k=5 paired comparison
resolves only 3.7% to 24.7%, that two real changes go undetected, and
that `roworder` -- an edit that provably cannot change what the circuit
computes -- is reported as an 11.8% regression. Everything now turns on
one question:

    is that spread NOISE, which an ensemble averages away, or BIAS,
    which it does not?

If noise, the paired minimum detectable difference falls as

    MDD(k) = z * s * sqrt(2/k)

so a 10% resolution at k=5 becomes 2% at k≈125 -- about two minutes of
wall-clock on a 64-core machine, and the gate is practical after all. If
it does not fall that way, no ensemble rescues it and a top-level gate
on this design is not possible by this route.

The same data answers the second question. If `roworder`'s +11.8% is
noise its estimated delta shrinks toward zero as k grows; if it is a real
QoR consequence of a semantically neutral edit -- which is exactly what
`split` turned out to be on the multiplier design, costing 9.6% -- the
delta stays put and only its interval shrinks. Those two look identical
at k=5 and completely different at k=41.

## Why one big ensemble instead of several

MDD at several k values does not need several runs. One ensemble of N
perturbations contains many subsets of size k, so the whole curve comes
out of a single batch by resampling. That turns an O(sum of k) experiment
into an O(N) one, which matters when a leaf costs ~40s on this design.

The perturbations are core-area nudges of -20..+20 whole sites. Twenty
sites is 1.08um on a 392um core -- 0.28%, still far below anything a
person would call a design change, and site-aligned so
initialize_floorplan has nothing to snap.
"""

import argparse
import json
import math
import os
import random
import shutil
import statistics
import tempfile

from optuna_study import run_estimator_batch, scratch_root

Z = 2.0

# The cheapest rung that still places macros, from the pre-flight: it had
# the best resolvable difference of the three and does not pay for global
# route, which added almost nothing to either spread or verdict and costs
# 742MB per ensemble member instead of 189MB.
#
# Every gating knob explicit, zeros included -- an omitted knob means
# "whatever ORFS defaults to", and GPL_TIMING_DRIVEN and
# GPL_ROUTABILITY_DRIVEN are real ORFS variables defaulted to 1.
RUNG = {
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

EPS = [e for e in range(-20, 21)]

K_VALUES = [5, 10, 20, 40]

# Enough resamples that the reported medians are stable; cheap, since
# this is arithmetic over data already collected.
RESAMPLES = 400


def achieved(leaf):
    with open(leaf, "r") as f:
        return max(p["min_period"] for p in json.load(f)["paths"])


def run_arm(exe, truth, label):
    """One ensemble: the whole perturbation set for a single variant."""
    manifest = {f"e{e}": dict(RUNG, CORE_AREA_EPS_SITES=str(e)) for e in EPS}
    scratch = tempfile.mkdtemp(prefix=f"kscale_{label}_", dir=scratch_root())
    leaves = os.path.join(scratch, "leaves")
    try:
        got = run_estimator_batch(
            exe, manifest, truth, parallel=True, keep_results_dir=leaves
        )
        out = {}
        for e in EPS:
            cid = f"e{e}"
            leaf = os.path.join(leaves, f"{cid}.json")
            if got.get(cid) is not None and os.path.exists(leaf):
                out[e] = achieved(leaf)
        return out
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def curve(base, variant, rng):
    """Paired delta and MDD as a function of ensemble size.

    Subsets of the shared perturbation set, so every k is measured on the
    same underlying runs and the comparison stays paired.
    """
    shared = sorted(set(base) & set(variant))
    diffs = {e: variant[e] - base[e] for e in shared}
    base_mean = statistics.fmean(base[e] for e in shared)
    rows = []
    for k in K_VALUES:
        if k > len(shared):
            continue
        mdds, deltas, called = [], [], 0
        for _ in range(RESAMPLES):
            pick = rng.sample(shared, k)
            d = [diffs[e] for e in pick]
            s = statistics.stdev(d)
            mdd = Z * s * math.sqrt(2.0 / k)
            mean_d = statistics.fmean(d)
            mdds.append(100.0 * mdd / base_mean)
            deltas.append(100.0 * mean_d / base_mean)
            if abs(mean_d) > mdd:
                called += 1
        rows.append(
            {
                "k": k,
                "mdd_pct": statistics.median(mdds),
                "delta_pct": statistics.median(deltas),
                "delta_spread_pct": statistics.stdev(deltas),
                "called_changed_frac": called / float(RESAMPLES),
            }
        )
    return rows, len(shared), 100.0 * statistics.fmean(diffs.values()) / base_mean


def prob_better(base, variant, rng, resamples=2000):
    """P(a draw from the variant beats a draw from the base).

    Every base-variant pair compared, ties at half, which is the
    Mann-Whitney statistic and the common-language effect size. Rank
    based, so the 25% spread and the absence of any correlation between
    the arms cost it nothing.

    The interval is a bootstrap over both ensembles rather than a normal
    approximation: with distributions this wide and this far from
    Gaussian, an analytic interval would be quoting a precision it does
    not have.
    """
    b = list(base.values())
    v = list(variant.values())
    if not b or not v:
        return None

    def stat(bs, vs):
        wins = sum(1.0 if x < y else (0.5 if x == y else 0.0) for y in bs for x in vs)
        return wins / (len(bs) * len(vs))

    point = stat(b, v)
    draws = sorted(
        stat(
            [rng.choice(b) for _ in b],
            [rng.choice(v) for _ in v],
        )
        for _ in range(resamples)
    )
    lo = draws[int(0.025 * resamples)]
    hi = draws[int(0.975 * resamples) - 1]
    return {"p": point, "lo": lo, "hi": hi}


def best_of_k(base, variant, rng, ks=(1, 4, 8), resamples=2000, boots=120):
    """Does the change improve the best of k tries?

    If the placer is a lottery, best-of-k is the operating point a design
    actually ships at, and it is a different question from the mean: a
    change can widen the distribution enough to win here while losing on
    average. Measured on this design, the two genuinely cross over.

    Reported with an interval, because without one this statistic invites
    exactly the wrong conclusion. The minimum of k draws is decided by the
    few smallest samples in the ensemble, so with 41 of them a best-of-8
    figure rests on a handful of points. The bootstrap resamples the
    ENSEMBLES rather than just the draws -- the uncertainty that matters
    is having only 41 observations of each distribution, not how many
    times we then draw from them.
    """
    b = list(base.values())
    v = list(variant.values())
    out = {}

    def p_win(bs, vs, k):
        wins = 0
        for _ in range(resamples):
            bm = min(rng.choice(bs) for _ in range(k))
            vm = min(rng.choice(vs) for _ in range(k))
            if vm < bm:
                wins += 1
        return wins / float(resamples)

    for k in ks:
        point = p_win(b, v, k)
        draws = sorted(
            p_win([rng.choice(b) for _ in b], [rng.choice(v) for _ in v], k)
            for _ in range(boots)
        )
        lo = draws[int(0.025 * boots)]
        hi = draws[int(0.975 * boots) - 1]
        out[k] = {
            "p_variant_better": point,
            "lo": lo,
            "hi": hi,
            "conclusive": not (lo <= 0.5 <= hi),
            "base_mean_best": statistics.fmean(
                min(rng.choice(b) for _ in range(k)) for _ in range(resamples)
            ),
            "variant_mean_best": statistics.fmean(
                min(rng.choice(v) for _ in range(k)) for _ in range(resamples)
            ),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base_exe")
    ap.add_argument("truth_json")
    ap.add_argument("design_name")
    ap.add_argument(
        "--variant",
        action="append",
        default=[],
        metavar="NAME:EXE",
        help="a variant to compare against the base",
    )
    args = ap.parse_args()

    rng = random.Random(1)
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()

    print(f"=== {args.design_name}: ensemble of {len(EPS)} perturbations per arm")
    base = run_arm(args.base_exe, args.truth_json, "base")
    print(f"base: {len(base)}/{len(EPS)} leaves")
    if len(base) < max(K_VALUES):
        raise SystemExit("too few base leaves to measure the curve")

    report = {
        "design": args.design_name,
        "rung": RUNG,
        "n_eps": len(EPS),
        "base_periods": {str(e): v for e, v in sorted(base.items())},
    }
    for spec in args.variant:
        name, exe = spec.split(":", 1)
        arm = run_arm(exe, args.truth_json, name)
        rows, n, full_delta = curve(base, arm, rng)
        pb = prob_better(base, arm, rng)
        bok = best_of_k(base, arm, rng)
        report[name] = {
            "rows": rows,
            "n_shared": n,
            "delta_all_pct": full_delta,
            "prob_better": pb,
            "best_of_k": bok,
            # Raw, so every statistic above can be recomputed later
            # without paying for the ensemble again.
            "periods": {str(e): v for e, v in sorted(arm.items())},
        }

        print(
            f"\n--- {name}: {n} shared perturbations, "
            f"delta over all of them {full_delta:+.2f}%"
        )
        print(
            f"{'k':>5s} {'MDD%':>8s} {'delta%':>9s} {'delta sd%':>10s} "
            f"{'called CHANGED':>15s} {'MDD x sqrt(k/5)':>16s}"
        )
        ref = rows[0]["mdd_pct"] if rows else float("nan")
        for r in rows:
            # If the spread is noise, MDD falls as 1/sqrt(k) and this
            # column stays flat at the k=5 value. If it is bias, it does
            # not.
            scaled = r["mdd_pct"] * math.sqrt(r["k"] / 5.0)
            print(
                f"{r['k']:>5d} {r['mdd_pct']:>7.2f}% {r['delta_pct']:>8.2f}% "
                f"{r['delta_spread_pct']:>9.2f}% "
                f"{100.0 * r['called_changed_frac']:>14.0f}% {scaled:>15.2f}%"
            )
        if rows:
            drift = abs(rows[-1]["mdd_pct"] * math.sqrt(rows[-1]["k"] / 5.0) - ref)
            verdict = (
                "noise (averages away)" if drift < 0.25 * ref else "NOT pure noise"
            )
            print(f"      scaling verdict: {verdict}")

        if pb:
            call = (
                "indistinguishable"
                if pb["lo"] <= 0.5 <= pb["hi"]
                else ("BETTER" if pb["p"] > 0.5 else "WORSE")
            )
            print(
                f"      P(change beats base) = {pb['p']:.3f} "
                f"[{pb['lo']:.3f}, {pb['hi']:.3f}]  -> {call}"
            )
        for k, d in sorted(bok.items()):
            mark = "" if d["conclusive"] else "  (inconclusive)"
            print(
                f"      best-of-{k}: change wins {100 * d['p_variant_better']:.0f}%"
                f" [{100 * d['lo']:.0f}-{100 * d['hi']:.0f}%]"
                f"  base {d['base_mean_best']:.1f} vs "
                f"change {d['variant_mean_best']:.1f}{mark}"
            )

    path = os.path.join(
        ws, "test/estimation_ladder", f"k_scaling_{args.design_name}.json"
    )
    with open(path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
