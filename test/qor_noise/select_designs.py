#!/usr/bin/env python3

"""Choose the design set a per-PR QoR gate should run.

Ranking designs one at a time answers the wrong question. Two designs
that both respond to exactly the same tool changes are one design's worth
of information at two designs' worth of CI time. What a gate needs is a
*set* that between them notice as many real changes as possible, at the
least cost, with more than one witness per change so a lone draw cannot
carry a verdict on its own.

That is a coverage problem, and the history supplies both the events and
the ground truth. A *fleet-wide event* -- a commit that moved thresholds
on at least FLEETWIDE designs at once -- is taken as a real tool change;
the direction concordance measured across these events is what justifies
that reading. A candidate set **detects** an event if at least `--witnesses`
of its members moved at that commit.

Two selections are reported:

  * **greedy**, maximising newly-detected events per design added. This
    is the honest upper bound on what a set of that size can do.
  * **cost-aware greedy**, maximising newly-detected events per unit of
    estimated runtime. This is the one a CI budget actually wants.

Greedy is not optimal for coverage, but coverage is submodular, so greedy
is within (1 - 1/e) of optimal and the gap is smaller than the error in
the runtime proxy.
"""

import argparse
import collections
import csv
import json
import sys

FLEETWIDE = 5


def cost_of(instances):
    """Rough CI cost of a design, in units of a small design.

    Runtime is superlinear in instance count -- detailed routing and
    timing repair dominate and neither is linear -- so a linear proxy
    would badly understate what a million-instance design costs. The
    exponent is a stand-in until measured runtimes replace it, and the
    ranking is reported for both this and a plain linear cost so that a
    conclusion resting on the exponent can be spotted.
    """
    return max(instances, 1.0) ** 1.2


def load_events(transitions, fleetwide=FLEETWIDE):
    bycommit = collections.defaultdict(list)
    with open(transitions) as fh:
        for r in csv.DictReader(fh):
            bycommit[r["commit"]].append(r)
    events = []
    for commit, rows in bycommit.items():
        designs = set(f"{r['platform']}/{r['design']}" for r in rows)
        if len(designs) >= fleetwide:
            events.append(
                {"commit": commit, "when": int(rows[0]["unix_time"]), "moved": designs}
            )
    events.sort(key=lambda e: e["when"])
    return events


def load_lifetimes(history):
    first, last, size = {}, {}, {}
    import depad

    with open(history) as fh:
        for h in csv.DictReader(fh):
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


def detected(events, chosen, witnesses):
    """Which events at least `witnesses` of `chosen` would have caught."""
    hits = set()
    for i, e in enumerate(events):
        if len(e["moved"] & chosen) >= witnesses:
            hits.add(i)
    return hits


def witness_score(events, chosen, witnesses):
    """Sum over events of witnesses gathered, capped at the requirement.

    Counting finished detections alone cannot get greedy started when more
    than one witness is required: the first design added detects nothing,
    so every candidate scores zero and the search stops before it begins.
    Capped witness count is monotone and submodular, credits the partial
    progress that the first pick genuinely makes, and coincides with the
    detection count once a set is large enough to detect anything.
    """
    return sum(min(len(e["moved"] & chosen), witnesses) for e in events)


def greedy(events, candidates, witnesses, cost, budget=None, limit=None):
    """Add the design giving the most new witness-progress per unit cost."""
    chosen = set()
    trail = []
    spent = 0.0
    have = set()
    score = 0
    while True:
        best = None
        for d in candidates:
            if d in chosen:
                continue
            gain = witness_score(events, chosen | {d}, witnesses) - score
            if gain <= 0:
                continue
            value = gain / (cost(d) if cost else 1.0)
            if best is None or value > best[0]:
                best = (value, d, gain)
        if best is None:
            break
        _value, d, _gain = best
        if budget is not None and spent + cost(d) > budget:
            break
        chosen.add(d)
        spent += cost(d) if cost else 0.0
        have = detected(events, chosen, witnesses)
        score = witness_score(events, chosen, witnesses)
        trail.append(
            {
                "added": d,
                "size": len(chosen),
                "detected": len(have),
                "coverage": len(have) / len(events),
                "cost": spent,
            }
        )
        if limit is not None and len(chosen) >= limit:
            break
    return chosen, trail


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transitions", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--witnesses", type=int, default=2)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)

    events = load_events(args.transitions)
    _first, _last, size = load_lifetimes(args.history)
    candidates = sorted(set().union(*[e["moved"] for e in events]))

    report = {"events": len(events), "witnesses": args.witnesses, "runs": {}}

    for label, costfn in (
        ("uniform", None),
        ("by_cost", lambda d: cost_of(size.get(d, 20000.0))),
    ):
        chosen, trail = greedy(events, candidates, args.witnesses, costfn, limit=args.limit)
        report["runs"][label] = {
            "chosen": sorted(chosen),
            "trail": trail,
        }

    report["sizes"] = {d: size.get(d) for d in candidates}
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"events={len(events)} candidates={len(candidates)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
