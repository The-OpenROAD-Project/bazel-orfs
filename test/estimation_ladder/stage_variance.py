"""Where in the flow is the noise born, and what KPI could resolve it?

The flow-side companion to seed_sensitivity.py.  That study measures
sigma_E -- the ESTIMATOR's stability under admissible perturbations --
and is explicit that the flow-side dispersion is out of its scope.  This
one drives stage_variance.tcl: the production ORFS stage scripts
floorplan..grt in one OpenROAD process, with an ensemble forked off each
stage boundary (place / cts / grt, plus an everything-at-once arm), every
member measured at grt by the same extract_lib instrument as the ground
truth.  See the walk's own header for the perturbation per arm and why.

Three questions, in decreasing order of how directly the data answers
them:

1. **Attribution.**  Each arm's spread is the noise born at that stage
   *as seen at flow end* -- amplification through the later stages is
   included by construction, because every member runs the production
   tail to grt.  Under independence the per-arm variances must add up to
   the all-arm's directly measured variance; the residual is the
   interaction term the per-stage measurement cannot see, and computing
   it is the study's validity check rather than an afterthought.

2. **KPI candidates, not a KPI decision.**  A PR gate needs a statistic
   of the (base, change) ensembles with a stated variance.  Which
   statistic is a compromise -- extremal KPIs track what tapeout cares
   about but inherit the tail's noise; aggregates average the tail away
   but measure something softer -- so this reports sigma and the
   resolvable effect delta_min = z * sigma * sqrt(2/k) for a MENU of
   candidates (max / quantiles / top-N means / mean over the sampled
   worst-25% paths, plus std-cell area), and the decision is made by
   whoever reads the table, once the compromises are numbers.  The KPI
   is PPA-shaped: performance and area now; power is recorded equal to
   area and left as a TODO (a credible power number needs switching
   activity the flow does not have at grt).

3. **The runtime-for-resolution menu.**  Each arm is also a candidate
   ensemble *generator* with its own marginal cost per member (a
   grt-only member costs a fraction of a place..grt member).  Per
   (generator, candidate, k) the table pairs c * k CPU-seconds against
   delta_min -- the Pareto menu a later gate decision picks from.

Determinism guards, free with the design: every arm carries a "null"
member with no perturbation, which a deterministic tool must reproduce
bit-for-bit equal to the spine's own leaf; and a clock nudge is read
back by the walk and verified here against base + eps, because a
silently inert perturbation would report zero noise everywhere.
"""

import argparse
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import tempfile

Z = 1.96  # two-sided 95%
K_GRID = [5, 10, 20, 40]
TOP_NS = [5, 10, 20]
QUANTILES = [0.90, 0.95, 0.99]
DEFAULT_GRT_SEEDS = list(range(1, 9))
# GPL seeds start at 2: global_placement's initial-place perturbation
# defaults to -random_seed 1, so seed 1 is the spine's own draw (measured
# bit-identical) and would be a second null, not a sample.
DEFAULT_GPL_SEEDS = list(range(2, 10))
DEFAULT_CTS_EPS = [-4, -3, -2, -1, 1, 2, 3, 4]
# Relative tolerances, from seed_sensitivity.py's floor analysis: OpenSTA
# keeps periods and slacks in float32, so "equal" means "to float32
# epsilon", three orders of magnitude below anything the study resolves.
NULL_RELTOL = 1e-6
NUDGE_RELTOL = 1e-6


def percentile(sorted_asc, q):
    """Linear-interpolation percentile of an already-sorted list."""
    if not sorted_asc:
        raise ValueError("empty sample")
    if len(sorted_asc) == 1:
        return sorted_asc[0]
    pos = q * (len(sorted_asc) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    frac = pos - lo
    return sorted_asc[lo] * (1 - frac) + sorted_asc[hi] * frac


def kpi_candidates(leaf):
    """The KPI menu, evaluated on one leaf's raw material.

    Every candidate is a statistic of the same sampled worst-25% path
    population (plus the tagged macro paths), so the comparison between
    candidates is about aggregation, not about what was sampled.
    """
    periods = sorted(p["min_period"] for p in leaf["paths"])
    if not periods:
        raise ValueError("leaf has no paths")
    desc = periods[::-1]
    area = leaf["area"]["stdcell_um2"]
    out = {
        "achieved": desc[0],
        "mean": statistics.fmean(periods),
    }
    trim = max(1, len(periods) // 10)
    if len(periods) > 2 * trim:
        out["trimmed_mean_10"] = statistics.fmean(periods[trim:-trim])
    for q in QUANTILES:
        out[f"p{int(q * 100)}"] = percentile(periods, q)
    for n in TOP_NS:
        if len(desc) >= n:
            out[f"top{n}_mean"] = statistics.fmean(desc[:n])
    out["area"] = area
    # TODO(power): recorded equal to std-cell area until the study needs
    # a real power figure (report_power under a stated activity).
    out["power_todo"] = leaf.get("power_todo", area)
    # One illustrative composite, not a recommendation: the unweighted
    # geometric mean of (performance, area, power:=area).
    out["ppa_geomean"] = (out["achieved"] * area * out["power_todo"]) ** (1.0 / 3.0)
    return out


def ensemble_stats(values):
    stats = {
        "n": len(values),
        "mean": statistics.fmean(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }
    stats["range"] = (stats["max"] - stats["min"]) if values else None
    if len(values) >= 2:
        stats["stdev"] = statistics.stdev(values)
        stats["cv"] = stats["stdev"] / stats["mean"] if stats["mean"] else None
    else:
        stats["stdev"] = None
        stats["cv"] = None
    return stats


def delta_min(sigma, k, z=Z):
    """Smallest per-arm shift resolvable from k members per arm."""
    return z * sigma * math.sqrt(2.0 / k)


def required_k(sigma, delta, z=Z):
    """Members per arm needed to resolve a shift of delta."""
    if delta <= 0:
        raise ValueError("delta must be positive")
    # The epsilon keeps ceil from charging an extra member when the
    # quotient is an integer up to float rounding.
    return math.ceil(2.0 * (z * sigma / delta) ** 2 - 1e-9)


def variance(values):
    return statistics.variance(values) if len(values) >= 2 else 0.0


def decompose(per_arm_values, all_values, resamples=2000, seed=0):
    """Sum-of-variances prediction vs the directly measured total.

    Under independence, var(place) + var(cts) + var(grt) predicts
    var(all).  The interaction term is the difference, with a bootstrap
    CI over members; a CI containing zero is consistency, not proof --
    and 'inconclusive' is a legal verdict when the CI is too wide to say
    either way (it always is at small k; the point is to say so).
    """
    parts = {arm: variance(vals) for arm, vals in per_arm_values.items()}
    predicted_var = sum(parts.values())
    measured_var = variance(all_values)
    interaction = measured_var - predicted_var

    rng = random.Random(seed)
    boots = []
    for _ in range(resamples):
        pred = 0.0
        for vals in per_arm_values.values():
            res = [rng.choice(vals) for _ in vals]
            pred += variance(res)
        res_all = [rng.choice(all_values) for _ in all_values]
        boots.append(variance(res_all) - pred)
    boots.sort()
    ci_lo = percentile(boots, 0.025)
    ci_hi = percentile(boots, 0.975)
    if ci_lo > 0:
        verdict = "under-counted: the arms miss interaction noise"
    elif ci_hi < 0:
        verdict = "over-counted: the arms double-book shared noise"
    else:
        verdict = "consistent (interaction CI contains zero)"
    return {
        "per_arm_var": parts,
        "predicted_sigma": math.sqrt(predicted_var),
        "measured_sigma": math.sqrt(measured_var),
        "interaction_var": interaction,
        "interaction_ci": [ci_lo, ci_hi],
        "verdict": verdict,
    }


def check_nulls(leaves, spine, candidates=("achieved", "mean", "area")):
    """A deterministic tool must reproduce the spine from a null member."""
    failures = []
    spine_kpis = kpi_candidates(spine)
    for arm in ("place", "cts", "grt"):
        leaf = leaves.get((arm, "null"))
        if leaf is None:
            failures.append(f"{arm}: null member missing (member crashed?)")
            continue
        kpis = kpi_candidates(leaf)
        for cand in candidates:
            a, b = spine_kpis[cand], kpis[cand]
            if abs(a - b) > NULL_RELTOL * max(abs(a), abs(b), 1e-30):
                failures.append(
                    f"{arm}/null {cand}: {b} != spine {a} -- the flow is "
                    "not deterministic under fork, or the harness leaks "
                    "state between members"
                )
    return failures


def check_nudges(leaves, spine, cts_eps, all_k):
    """A nudge that did not land is an error, not a zero."""
    failures = []
    base = spine["clock_period"]

    def expect(arm, tag, eps):
        leaf = leaves.get((arm, str(tag)))
        if leaf is None:
            return  # crashed member: reported elsewhere, not a nudge bug
        want = base + eps
        got = leaf["clock_period"]
        if abs(got - want) > NUDGE_RELTOL * abs(want):
            failures.append(
                f"{arm}/{tag}: clock_period {got}, expected {want} "
                "-- the nudge did not land"
            )

    for eps in cts_eps:
        expect("cts", eps, eps)
    for i in range(1, all_k + 1):
        expect("all", i, cts_eps[(i - 1) % len(cts_eps)])
    return failures


def analyze(leaves, walk, cts_eps, all_k, design="multiplier_top", gpl_seeds=None):
    """Pure aggregation: leaves + walk metadata -> the result document."""
    spine = leaves[("spine", "base")]
    spine_kpis = kpi_candidates(spine)
    candidates = sorted(spine_kpis)

    arms = {}
    per_arm_kpis = {}
    for arm in ("place", "cts", "grt", "all"):
        members = {
            tag: leaf
            for (a, tag), leaf in leaves.items()
            if a == arm and tag != "null"
        }
        kpis = {tag: kpi_candidates(leaf) for tag, leaf in members.items()}
        per_arm_kpis[arm] = kpis
        arms[arm] = {
            "tags": sorted(members),
            "tail_s": {tag: leaf["tail_s"] for tag, leaf in members.items()},
            "median_tail_s": (
                statistics.median(leaf["tail_s"] for leaf in members.values())
                if members
                else None
            ),
            "kpis": kpis,
            "stats": {
                cand: ensemble_stats([k[cand] for k in kpis.values() if cand in k])
                for cand in candidates
            },
            # Raw material so a future candidate can be evaluated without
            # re-running the flow: the full sampled min_period population
            # per member, macro paths tagged.
            "raw": {
                tag: {
                    "clock_period": leaf["clock_period"],
                    "wns": leaf["wns"],
                    "min_periods": [p["min_period"] for p in leaf["paths"]],
                    "macro_flags": [p["macro_path"] for p in leaf["paths"]],
                    "area": leaf["area"],
                }
                for tag, leaf in members.items()
            },
        }

    decomposition = {}
    for cand in candidates:
        per_arm = {
            arm: [k[cand] for k in per_arm_kpis[arm].values() if cand in k]
            for arm in ("place", "cts", "grt")
        }
        all_vals = [k[cand] for k in per_arm_kpis["all"].values() if cand in k]
        if all(len(v) >= 2 for v in per_arm.values()) and len(all_vals) >= 2:
            decomposition[cand] = decompose(per_arm, all_vals)

    # The same-GPL-seed pairing between the place and all arms: all-arm
    # member i drew gpl_seeds[(i-1) % len] as its placement seed, so its
    # delta against that place-arm member is the incremental spread the
    # cts nudge + GRT seed add on top of an identical placement.
    gpl_seeds = gpl_seeds or DEFAULT_GPL_SEEDS
    paired = {}
    pairs = [
        (str(i), str(gpl_seeds[(i - 1) % len(gpl_seeds)]))
        for i in range(1, all_k + 1)
    ]
    pairs = [
        (a, p)
        for a, p in pairs
        if a in per_arm_kpis["all"] and p in per_arm_kpis["place"]
    ]
    for cand in candidates:
        deltas = [
            per_arm_kpis["all"][a][cand] - per_arm_kpis["place"][p][cand]
            for a, p in pairs
            if cand in per_arm_kpis["all"][a] and cand in per_arm_kpis["place"][p]
        ]
        if len(deltas) >= 2:
            paired[cand] = ensemble_stats(deltas)

    # The menu: per (generator arm, candidate, k), what an ensemble costs
    # and what it can resolve.  Costs are marginal (the tail a member
    # re-runs); the spine prefix is paid once per ensemble, not per
    # member, and is reported separately in walk.json.
    pareto = []
    for arm in ("grt", "cts", "place", "all"):
        c = arms[arm]["median_tail_s"]
        if c is None:
            continue
        for cand in candidates:
            sigma = arms[arm]["stats"][cand]["stdev"]
            base = spine_kpis[cand]
            if sigma is None or not base:
                continue
            for k in K_GRID:
                d = delta_min(sigma, k)
                pareto.append(
                    {
                        "generator": arm,
                        "kpi": cand,
                        "k": k,
                        "cpu_s": c * k,
                        "delta_min": d,
                        "delta_min_pct": 100.0 * d / abs(base),
                    }
                )

    return {
        "design": design,
        "time_unit": spine["time_unit"],
        "params": {"cts_eps": cts_eps, "all_k": all_k, "z": Z, "k_grid": K_GRID},
        "spine": {
            "kpis": spine_kpis,
            "steps": walk.get("spine_steps", {}),
            "prefix_s": walk.get("prefix_s"),
            "clock_period": spine["clock_period"],
        },
        "arms": arms,
        "decomposition": decomposition,
        "paired_all_minus_place": paired,
        "pareto": pareto,
        "guards": {
            "null_failures": check_nulls(leaves, spine),
            "nudge_failures": check_nudges(leaves, spine, cts_eps, all_k),
        },
    }


def load_leaves(out_dir):
    leaves = {}
    walk = {}
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(out_dir, name)) as f:
            doc = json.load(f)
        if name == "walk.json":
            walk = doc
        else:
            leaves[(doc["arm"], str(doc["tag"]))] = doc
    return leaves, walk


def run_walk(exe, out_dir, work_dir, jobs, args):
    # Imported here, not at module level: optuna_study drags in the
    # optuna wheel, which the pure-math test (stage_variance_test.py,
    # the only CI-visible piece) has no business depending on.
    from optuna_study import scratch_root

    cmd = [
        exe,
        f"SV_OUT_DIR={os.path.abspath(out_dir)}",
        f"SV_WORK={os.path.abspath(work_dir)}",
        f"LOG_DIR={os.path.abspath(work_dir)}/log",
        "NUM_CORES=1",
        f"ORFS_FORK_JOBS={jobs}",
        f"SV_GRT_SEEDS={' '.join(str(s) for s in args.grt_seeds)}",
        f"SV_GPL_SEEDS={' '.join(str(s) for s in args.gpl_seeds)}",
        f"SV_CTS_EPS={' '.join(str(e) for e in args.cts_eps)}",
        f"SV_ALL_K={args.all_k}",
        f"SV_CHILD_TIMEOUT={args.child_timeout}",
    ]
    if args.keep_work:
        cmd.append("SV_KEEP_WORK=1")
    env = os.environ.copy()
    env["TMPDIR"] = scratch_root()
    print("stage_variance: running the walk (one process, forked members)")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    tail = []
    for line in proc.stdout:
        tail.append(line)
        tail = tail[-200:]
        if line.startswith("stage_variance:"):
            print(f"  {line.rstrip()}", flush=True)
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"walk exited {rc}\n" + "".join(tail))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", help="stage_variance_top_executable path")
    parser.add_argument("design", help="design name (output file suffix)")
    parser.add_argument(
        "--jobs",
        type=int,
        default=max(1, (os.cpu_count() or 8) // 2),
        help="concurrent forked members; each is single-threaded, and the "
        "README's oversubscription rule applies (jobs ~ cores/2 leaves "
        "headroom for the members' memory divergence)",
    )
    parser.add_argument("--grt-seeds", type=int, nargs="+", default=DEFAULT_GRT_SEEDS)
    parser.add_argument("--gpl-seeds", type=int, nargs="+", default=DEFAULT_GPL_SEEDS)
    parser.add_argument("--cts-eps", type=int, nargs="+", default=DEFAULT_CTS_EPS)
    parser.add_argument("--all-k", type=int, default=8)
    parser.add_argument("--child-timeout", type=int, default=10800)
    parser.add_argument(
        "--reuse", help="analyze an existing SV_OUT_DIR instead of running"
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="keep every member's results/ tree (disk!) and the walk dir",
    )
    args = parser.parse_args()

    if args.reuse:
        out_dir = args.reuse
        work = None
    else:
        from optuna_study import scratch_root

        work = tempfile.mkdtemp(prefix="stage_variance_", dir=scratch_root())
        out_dir = os.path.join(work, "leaves")
        run_walk(args.executable, out_dir, os.path.join(work, "sv"), args.jobs, args)

    try:
        leaves, walk = load_leaves(out_dir)
        if ("spine", "base") not in leaves:
            raise RuntimeError("the spine leaf is missing; the walk did not finish")
        result = analyze(
            leaves,
            walk,
            args.cts_eps,
            args.all_k,
            design=args.design,
            gpl_seeds=args.gpl_seeds,
        )

        failures = (
            result["guards"]["null_failures"] + result["guards"]["nudge_failures"]
        )
        expected = (
            len(args.gpl_seeds) + len(args.grt_seeds) + len(args.cts_eps) + args.all_k + 4
        )
        got = len(leaves)
        print(f"stage_variance: {got}/{expected} leaves")
        for cand, dec in result["decomposition"].items():
            print(
                f"  {cand}: predicted sigma {dec['predicted_sigma']:.4g}, "
                f"measured {dec['measured_sigma']:.4g} -- {dec['verdict']}"
            )
        for f in failures:
            print(f"  GUARD FAILURE: {f}")

        ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())
        out_json = os.path.join(
            ws, "test", "estimation_ladder", f"stage_variance_{args.design}.json"
        )
        with open(out_json, "w") as f:
            json.dump(result, f, indent=1)
        print(f"stage_variance: wrote {out_json}")
        if failures:
            raise SystemExit("stage_variance: guard failures (see above)")
    finally:
        if work and not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
