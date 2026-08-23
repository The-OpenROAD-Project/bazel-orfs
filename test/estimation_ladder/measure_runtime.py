"""Rung B of the estimation ladder study: adaptive runtime measurement.

Rung A knows every configuration's accuracy but nothing trustworthy
about its runtime.  This rung fills that in, one estimator process at a
time so nothing competes for the machine, with whatever thread count
ORFS hands the tool -- the question is how fast the estimator goes on
the whole machine, not how it behaves pinned to one core.

Measuring every archived configuration would cost hours, and measuring
an arbitrary ten of them tends to produce ten points bunched at one end
of the range.  Which configurations would spread the front out is not
knowable in advance, so this is an active-learning loop: fit a surrogate
for runtime, measure wherever the surrogate is least certain *and* the
front has a hole, refit, repeat.

Two details do most of the work:

  * Everything is done in log10(runtime).  The rungs span roughly
    0.02 s to 600 s; on a linear axis nine of ten points would land in
    the last decade and "evenly spread" would be meaningless.

  * The surrogate predicts each *phase* separately and sums.  Phase
    runtimes depend on disjoint knob subsets -- global routing knobs say
    nothing about how long placement takes -- so the per-phase model
    learns far faster than one black box over the total would.
"""

import argparse
import json
import math
import os
import statistics
import zlib

from sklearn.ensemble import RandomForestRegressor

from optuna_study import run_estimator

# Stop when the front carries at least this many points and no gap along
# it exceeds MAX_GAP.  Ten evenly spread points leave gaps of about
# 1/9 = 0.11, so 0.15 tolerates real structure -- knees, clusters --
# without accepting a hole.
TARGET_POINTS = 10
MAX_GAP = 0.15
# A backstop so a pathological front cannot run forever.  If this is hit
# with the gap criterion unmet, the report says so rather than implying
# the front was filled.
MAX_MEASUREMENTS = 25
REPEATS = 3
# Above this coefficient of variation the repeats disagree enough that
# the median is not yet trustworthy.
CV_TOLERANCE = 0.05
MAX_REPEATS = 7
# Rung B only ever times configurations that already finished inside rung
# A's own timeout, so this is a guard against a hang rather than a real
# bound on the search.
RUN_TIMEOUT = 3600.0


def featurize(env, keys):
    """Encode an estimator environment as a numeric vector.

    Values are mostly numbers or flags; anything else is hashed into an
    integer, which is all a tree ensemble needs from a category.  crc32
    rather than hash(): str hashing is salted per process, so the same
    configuration would featurize differently between runs.
    """
    row = []
    for k in keys:
        v = env.get(k, "")
        if v == "":
            row.append(-1.0)
            continue
        try:
            row.append(float(v))
        except ValueError:
            row.append(float(zlib.crc32(v.encode()) % 1000))
    return row


def measure(estimator_exe, env, ground_truth_json):
    """Time one configuration, repeating until the repeats agree."""
    runtimes = []
    metrics = None
    while len(runtimes) < MAX_REPEATS:
        metrics = run_estimator(
            estimator_exe, env, ground_truth_json, timeout_s=RUN_TIMEOUT
        )
        runtimes.append(metrics["runtime_s"])
        if len(runtimes) >= REPEATS:
            med = statistics.median(runtimes)
            if med <= 0:
                break
            sd = statistics.pstdev(runtimes)
            if sd / med <= CV_TOLERANCE:
                break
    return statistics.median(runtimes), runtimes, metrics


def pareto_front(points, accuracy_key):
    """Non-dominated points: faster is better, and for the accuracy axis
    smaller is better (callers pass an error-like metric)."""
    front = []
    for p in points:
        dominated = any(
            q is not p
            and q["runtime_s"] <= p["runtime_s"]
            and q[accuracy_key] <= p[accuracy_key]
            and (q["runtime_s"] < p["runtime_s"] or q[accuracy_key] < p[accuracy_key])
            for q in points
        )
        if not dominated:
            front.append(p)
    return sorted(front, key=lambda p: p["runtime_s"])


def normalized_gaps(front):
    """Gaps between consecutive front points along log10(runtime),
    normalized to the front's own span."""
    if len(front) < 2:
        return []
    logs = [math.log10(max(p["runtime_s"], 1e-6)) for p in front]
    span = logs[-1] - logs[0]
    if span <= 0:
        return [0.0] * (len(logs) - 1)
    return [(b - a) / span for a, b in zip(logs, logs[1:])]


def gap_for(front, predicted_log):
    """Size of the front gap a predicted runtime would land in.  A
    prediction outside the current range is credited with the largest
    gap: extending the front is at least as valuable as subdividing it."""
    gaps = normalized_gaps(front)
    if not gaps:
        return 1.0
    logs = [math.log10(max(p["runtime_s"], 1e-6)) for p in front]
    if predicted_log <= logs[0] or predicted_log >= logs[-1]:
        return max(gaps + [1.0])
    for i, (a, b) in enumerate(zip(logs, logs[1:])):
        if a <= predicted_log <= b:
            return gaps[i]
    return max(gaps)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("estimator_exe")
    ap.add_argument("ground_truth_json")
    ap.add_argument("design_name")
    ap.add_argument("--archive", required=True, help="rung A archive JSON")
    ap.add_argument("--accuracy-key", default="mean_rel_err")
    args = ap.parse_args()

    # bazel runs this from a runfiles tree, so a relative --archive is
    # resolved against the workspace where rung A wrote it.
    archive_path = args.archive
    if not os.path.isabs(archive_path):
        ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
        if ws and not os.path.exists(archive_path):
            archive_path = os.path.join(ws, "test/estimation_ladder", args.archive)
    if not os.path.exists(archive_path):
        raise SystemExit(f"archive not found: {archive_path}; run rung A first")
    with open(archive_path) as f:
        archive = json.load(f)
    if not archive:
        raise SystemExit("empty archive; run rung A first")

    keys = sorted({k for row in archive for k in row["env"]})
    candidates = {i: row for i, row in enumerate(archive)}

    # Seed at the rung extremes so the surrogate sees the full dynamic
    # range before it is asked to extrapolate anything.
    def rung_depth(row):
        env = row["env"]
        return (
            int(env.get("RUN_PLACE", 0) or 0)
            + (1 if env.get("CLOCK_MODE") == "real" else 0)
            + int(env.get("RUN_GRT", 0) or 0)
            + int(env.get("RUN_REPAIR_TIMING", 0) or 0)
        )

    by_depth = sorted(candidates, key=lambda i: rung_depth(candidates[i]))
    seeds = [
        by_depth[0],
        by_depth[len(by_depth) // 3],
        by_depth[2 * len(by_depth) // 3],
        by_depth[-1],
    ]
    seeds = list(dict.fromkeys(seeds))

    measured = {}
    pending = list(seeds)

    while True:
        while pending:
            idx = pending.pop(0)
            row = candidates[idx]
            runtime, repeats, metrics = measure(
                args.estimator_exe, row["env"], args.ground_truth_json
            )
            measured[idx] = {
                "index": idx,
                "env": row["env"],
                "runtime_s": runtime,
                "repeats": repeats,
                "phases": metrics["phases"],
                **{
                    k: v for k, v in metrics.items() if k not in ("phases", "runtime_s")
                },
            }
            print(
                f"measured #{idx}: {runtime:.3f}s "
                f"{args.accuracy_key}={measured[idx][args.accuracy_key]:.4f} "
                f"({len(measured)} total)"
            )

        points = list(measured.values())
        front = pareto_front(points, args.accuracy_key)
        gaps = normalized_gaps(front)
        worst_gap = max(gaps) if gaps else 1.0

        if len(front) >= TARGET_POINTS and worst_gap <= MAX_GAP:
            print(f"converged: {len(front)} front points, worst gap {worst_gap:.3f}")
            break
        if len(measured) >= MAX_MEASUREMENTS:
            print(
                f"stopped at the {MAX_MEASUREMENTS}-measurement cap with "
                f"{len(front)} front points and a worst gap of {worst_gap:.3f} "
                f"(target {MAX_GAP}); the front has a hole this budget did not fill"
            )
            break

        # Refit the per-phase surrogate on log10 runtime.
        phase_names = sorted({p for m in measured.values() for p in m["phases"]})
        X = [featurize(m["env"], keys) for m in measured.values()]
        models = {}
        for phase in phase_names:
            y = [
                math.log10(max(m["phases"].get(phase, 0.0), 1e-4))
                for m in measured.values()
            ]
            model = RandomForestRegressor(n_estimators=100, random_state=1)
            model.fit(X, y)
            models[phase] = model

        best = None
        for idx, row in candidates.items():
            if idx in measured:
                continue
            x = [featurize(row["env"], keys)]
            total = 0.0
            var = 0.0
            for phase, model in models.items():
                preds = [t.predict(x)[0] for t in model.estimators_]
                total += 10 ** (sum(preds) / len(preds))
                var += statistics.pvariance(preds)
            sigma = math.sqrt(var)
            score = sigma * gap_for(front, math.log10(max(total, 1e-6)))
            if best is None or score > best[0]:
                best = (score, idx)

        if best is None:
            print("no unmeasured candidates left")
            break
        pending.append(best[1])

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.environ.get("PWD", ".")
    out = os.path.join(
        ws, "test/estimation_ladder", f"runtime_front_{args.design_name}.json"
    )
    with open(out, "w") as f:
        json.dump(
            {
                "measured": sorted(measured.values(), key=lambda m: m["runtime_s"]),
                "front": pareto_front(list(measured.values()), args.accuracy_key),
                "accuracy_key": args.accuracy_key,
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
