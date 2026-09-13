#!/usr/bin/env python3

"""Compute every number the report quotes, and write them to one JSON.

Nothing downstream of this file recomputes a statistic, and nothing in
the report is typed by hand. If a number appears in the write-up and not
in this file's output, it is a mistake.

The analysis has three parts, in increasing order of how much they are
allowed to claim:

1. **Corpus.** What the history contains: designs, platforms, metrics,
   span, and how thresholds were allowed to move. Descriptive only.

2. **Events.** Commits that moved thresholds on many designs at once, and
   how coherent those moves were. Direction concordance is what licenses
   reading these as tool changes rather than coincidence.

3. **Selection.** How much of the event record a given set of designs
   would have caught. Scored on a *held-out* second half of history,
   because a selection tuned on the events it is scored against will
   flatter itself, and did.
"""

import argparse
import bisect
import collections
import csv
import datetime
import json
import random
import statistics
import sys

import depad
from select_designs import cost_of, detected, greedy, load_events

FLEETWIDE = 5
WITNESSES = 2
DRAWS = 600
SIZE_CLASSES = [(1000, "tiny"), (10000, "small"), (100000, "mid"), (10**12, "any")]
D_GRID = [4, 6, 8, 10, 12, 16, 20, 24, 32, 40]


def read(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def lifetimes_and_sizes(history):
    first, last, size = {}, {}, {}
    for h in history:
        key = f"{h['platform']}/{h['design']}"
        t = int(h["unix_time"])
        first[key] = min(first.get(key, t), t)
        last[key] = max(last.get(key, t), t)
        if h["metric"] == "placeopt__design__instance__count__stdcell":
            try:
                v = depad.depad(h["metric"], float(h["value"]))
            except (TypeError, ValueError, depad.NotDepaddable):
                continue
            if key not in size or t >= size[key][0]:
                size[key] = (t, v)
    return first, last, {k: v for k, (_t, v) in size.items()}


def quantiles(values, ps):
    v = sorted(values)
    if not v:
        return {}
    return {f"p{int(p * 100):02d}": v[min(len(v) - 1, int(len(v) * p))] for p in ps}


def corpus_summary(history, labels, transitions):
    designs = set((h["platform"], h["design"]) for h in history)
    times = [int(h["unix_time"]) for h in history]
    kinds = collections.Counter(
        (t["kind"], t["retargeted"] == "1") for t in transitions
    )
    sizes_by_kind = {}
    for kind in ("tighten", "failing"):
        for rt in (False, True):
            rel = [
                abs(float(t["rel_change"]))
                for t in transitions
                if t["kind"] == kind and (t["retargeted"] == "1") == rt
            ]
            if rel:
                sizes_by_kind[f"{kind}_retargeted={int(rt)}"] = {
                    "n": len(rel),
                    **quantiles(rel, [0.5, 0.9, 0.99]),
                    "max": max(rel),
                }
    return {
        "rows": len(history),
        "designs": len(designs),
        "platforms": sorted(set(h["platform"] for h in history)),
        "metrics": len(set(h["metric"] for h in history)),
        "first": str(datetime.date.fromtimestamp(min(times))),
        "last": str(datetime.date.fromtimestamp(max(times))),
        "label_types": dict(collections.Counter(l["type"] for l in labels)),
        "labelled_rows": len(labels),
        "transition_kinds": {
            f"{k}_retargeted={int(r)}": n for (k, r), n in kinds.items()
        },
        "transition_sizes": sizes_by_kind,
    }


def event_summary(transitions, first, last, subjects):
    bycommit = collections.defaultdict(list)
    for t in transitions:
        bycommit[t["commit"]].append(t)

    per_commit_designs = collections.Counter(
        len(set((r["platform"], r["design"]) for r in v)) for v in bycommit.values()
    )

    events = []
    for commit, rows in bycommit.items():
        designs = set(f"{r['platform']}/{r['design']}" for r in rows)
        if len(designs) < FLEETWIDE:
            continue
        when = int(rows[0]["unix_time"])
        fleet = sum(1 for k in first if first[k] <= when <= last[k])
        kinds = collections.Counter(r["kind"] for r in rows)
        events.append(
            {
                "commit": commit,
                "when": when,
                "moved": len(designs),
                "fleet": fleet,
                "fraction": len(designs) / fleet if fleet else None,
                "concordance": max(kinds.values()) / sum(kinds.values()),
                "names": len(set(d.split("/", 1)[1] for d in designs)),
                "platforms": len(set(d.split("/", 1)[0] for d in designs)),
                "subject": subjects.get(commit, ""),
            }
        )
    events.sort(key=lambda e: e["when"])

    bump = [e for e in events if "update-openroad" in e["subject"]]
    return {
        "commits_moving_thresholds": len(bycommit),
        "designs_moved_per_commit": dict(sorted(per_commit_designs.items())),
        "solo_commits": per_commit_designs.get(1, 0),
        "fleetwide_threshold": FLEETWIDE,
        "fleetwide_events": len(events),
        "fraction_moved": {
            **quantiles([e["fraction"] for e in events], [0.1, 0.25, 0.5, 0.75, 0.9]),
            "mean": statistics.mean(e["fraction"] for e in events),
        },
        "concordance": {
            "median": statistics.median(e["concordance"] for e in events),
            "min": min(e["concordance"] for e in events),
            "fraction_at_100pct": sum(1 for e in events if e["concordance"] == 1.0)
            / len(events),
        },
        "distinct_names_median": statistics.median(e["names"] for e in events),
        "distinct_platforms_median": statistics.median(e["platforms"] for e in events),
        "single_name_events": sum(1 for e in events if e["names"] == 1),
        "openroad_bump_events": {
            "n": len(bump),
            "fraction_moved_median": (
                statistics.median(e["fraction"] for e in bump) if bump else None
            ),
            "concordance_min": min(e["concordance"] for e in bump) if bump else None,
            "all_fully_concordant": (
                all(e["concordance"] == 1.0 for e in bump) if bump else None
            ),
        },
    }


def selection_study(events, sizes, seed=17):
    """Score design sets on held-out events. This is where honesty lives."""
    events = sorted(events, key=lambda e: e["when"])
    split = len(events) // 2
    train, test = events[:split], events[split:]
    cand_train = sorted(set().union(*[e["moved"] for e in train]))
    cand_test = sorted(set().union(*[e["moved"] for e in test]))
    rng = random.Random(seed)

    def cov(subset, on):
        return len(detected(on, set(subset), WITNESSES)) / len(on)

    # Greedy fit on train, scored on both -- the overfitting check.
    greedy_rows = []
    for cap, label in SIZE_CLASSES:
        pool = [d for d in cand_train if sizes.get(d, 2e4) <= cap]
        if len(pool) < 8:
            continue
        _chosen, trail = greedy(train, pool, WITNESSES, None, limit=16)
        for D in (8, 12, 16):
            if len(trail) < D:
                continue
            s = [t["added"] for t in trail[:D]]
            rpool = [d for d in cand_test if sizes.get(d, 2e4) <= cap]
            rnd = [
                cov(rng.sample(rpool, min(D, len(rpool))), test) for _ in range(DRAWS)
            ]
            greedy_rows.append(
                {
                    "size_class": label,
                    "D": D,
                    "train_coverage": cov(s, train),
                    "test_coverage": cov(s, test),
                    "random_test_mean": statistics.mean(rnd),
                    "random_test_2sigma": 2 * statistics.stdev(rnd),
                    "designs": s,
                }
            )

    # Random sets by size class -- does identity or size matter at all?
    random_rows = []
    for cap, label in SIZE_CLASSES:
        pool = [d for d in cand_test if sizes.get(d, 2e4) <= cap]
        for D in D_GRID:
            if len(pool) < D:
                continue
            vals = [cov(rng.sample(pool, D), test) for _ in range(DRAWS)]
            costs = [
                sum(cost_of(sizes.get(d, 2e4)) for d in rng.sample(pool, D))
                for _ in range(200)
            ]
            random_rows.append(
                {
                    "size_class": label,
                    "pool": len(pool),
                    "exhausted": len(pool) == D,
                    "D": D,
                    "coverage_mean": statistics.mean(vals),
                    "coverage_2sigma": (
                        2 * statistics.stdev(vals) if len(set(vals)) > 1 else 0.0
                    ),
                    "cost_mean": statistics.mean(costs),
                }
            )

    # The practical recommendation: just take the cheapest D.
    cheapest = sorted(cand_test, key=lambda d: sizes.get(d, 2e4))
    cheap_rows = []
    for D in D_GRID:
        if len(cheapest) < D:
            continue
        s = cheapest[:D]
        cheap_rows.append(
            {
                "D": D,
                "coverage": cov(s, test),
                "total_instances": sum(sizes.get(d, 2e4) for d in s),
                "platforms": len(set(d.split("/", 1)[0] for d in s)),
                "largest": max(s, key=lambda d: sizes.get(d, 2e4)),
                "designs": s,
            }
        )

    return {
        "train_events": len(train),
        "test_events": len(test),
        "train_span": [
            str(datetime.date.fromtimestamp(train[0]["when"])),
            str(datetime.date.fromtimestamp(train[-1]["when"])),
        ],
        "test_span": [
            str(datetime.date.fromtimestamp(test[0]["when"])),
            str(datetime.date.fromtimestamp(test[-1]["when"])),
        ],
        "witnesses": WITNESSES,
        "greedy_vs_random": greedy_rows,
        "random_by_class": random_rows,
        "cheapest_d": cheap_rows,
        "fleet_total_instances": sum(sizes.get(d, 2e4) for d in cand_test),
    }


def design_table(transitions, first, last, sizes):
    bycommit = collections.defaultdict(list)
    for t in transitions:
        bycommit[t["commit"]].append(t)
    fleetwide, solo = [], collections.Counter()
    for _c, rows in bycommit.items():
        designs = set(f"{r['platform']}/{r['design']}" for r in rows)
        when = int(rows[0]["unix_time"])
        if len(designs) >= FLEETWIDE:
            fleetwide.append((when, designs))
        elif len(designs) == 1:
            solo[next(iter(designs))] += 1
    fleetwide.sort()
    times = [t for t, _ in fleetwide]
    year = 365.25 * 24 * 3600
    out = []
    for key in sorted(first):
        lo, hi = first[key], last[key]
        eligible = fleetwide[
            bisect.bisect_left(times, lo) : bisect.bisect_right(times, hi)
        ]
        if len(eligible) < 5:
            continue
        moved = sum(1 for _t, ds in eligible if key in ds)
        years = max((hi - lo) / year, 1e-9)
        out.append(
            {
                "design": key,
                "events_eligible": len(eligible),
                "responsiveness": moved / len(eligible),
                "solo_per_year": solo.get(key, 0) / years,
                "instances": sizes.get(key),
            }
        )
    out.sort(key=lambda r: -r["responsiveness"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", required=True)
    ap.add_argument("--transitions", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--subjects", required=True, help="commit<TAB>subject")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    history = read(args.history)
    transitions = read(args.transitions)
    labels = read(args.labels)
    subjects = {}
    with open(args.subjects) as fh:
        for line in fh:
            h, _, s = line.rstrip("\n").partition("\t")
            subjects[h] = s

    first, last, sizes = lifetimes_and_sizes(history)
    events = load_events(args.transitions)

    out = {
        "corpus": corpus_summary(history, labels, transitions),
        "events": event_summary(transitions, first, last, subjects),
        "designs": design_table(transitions, first, last, sizes),
        "selection": selection_study(events, sizes),
        "notes": {
            "timing_censoring": depad.TIMING_IS_CENSORED,
            "high_resolution_metrics": depad.HIGH_RESOLUTION,
        },
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
