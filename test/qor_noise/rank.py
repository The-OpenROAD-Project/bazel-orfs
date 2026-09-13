#!/usr/bin/env python3

"""Rank designs by how much they tell you about a tool change.

The question a PR gate has to answer is not "is this design interesting"
but "if the tool changed, would this design notice, and would I believe
it when it did". Three numbers decide that, and all three are already in
ORFS's history:

  * **responsiveness** -- of the fleet-wide events that occurred while
    this design was in the fleet, in what fraction did this design move?
    A fleet-wide event is a commit that moved thresholds on many designs
    at once; empirically those are the tool changes. A design that sat
    still through all of them is a passenger: running it costs CI time
    and returns no information.

  * **solo rate** -- how often did this design move on its own, when
    nothing else in the fleet did? A coherent tool change moves many
    designs in the same direction; a draw moves one. Solo moves are the
    closest thing the history has to a per-design noise rate.

  * **cost** -- design size, taken as the de-padded post-placement
    instance count. It is a proxy for runtime, and it is free, which
    matters because the ranking has to exist before anyone spends an
    evening timing 78 designs.

The ratio that matters is responsiveness per unit cost, with solo rate as
the penalty: a design that moves for everything, including nothing, is a
smoke detector wired to the toaster.
"""

import argparse
import bisect
import collections
import csv
import json
import sys

import depad

FLEETWIDE = 5  # designs moved in one commit before it counts as fleet-wide
SECONDS_PER_YEAR = 365.25 * 24 * 3600


def load(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transitions", required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-events", type=int, default=5)
    args = ap.parse_args(argv)

    trans = load(args.transitions)
    hist = load(args.history)

    # Lifetime of each design in the fleet.
    first, last = {}, {}
    for h in hist:
        key = (h["platform"], h["design"])
        t = int(h["unix_time"])
        first[key] = min(first.get(key, t), t)
        last[key] = max(last.get(key, t), t)

    # Latest de-padded size, as a runtime proxy.
    size = {}
    for h in hist:
        if h["metric"] != "placeopt__design__instance__count__stdcell":
            continue
        key = (h["platform"], h["design"])
        try:
            value = depad.depad(h["metric"], float(h["value"]))
        except (TypeError, ValueError, depad.NotDepaddable):
            continue
        t = int(h["unix_time"])
        if key not in size or t >= size[key][0]:
            size[key] = (t, value)

    bycommit = collections.defaultdict(list)
    for r in trans:
        bycommit[r["commit"]].append(r)

    fleetwide = []  # (time, {designs moved})
    solo = collections.Counter()
    for _commit, v in bycommit.items():
        designs = set((r["platform"], r["design"]) for r in v)
        when = int(v[0]["unix_time"])
        if len(designs) >= FLEETWIDE:
            fleetwide.append((when, designs))
        elif len(designs) == 1:
            solo[next(iter(designs))] += 1
    fleetwide.sort()
    event_times = [t for t, _ in fleetwide]

    out = []
    for key in sorted(first):
        platform, design = key
        lo, hi = first[key], last[key]
        i = bisect.bisect_left(event_times, lo)
        j = bisect.bisect_right(event_times, hi)
        eligible = fleetwide[i:j]
        if len(eligible) < args.min_events:
            continue
        moved = sum(1 for _t, ds in eligible if key in ds)
        years = max((hi - lo) / SECONDS_PER_YEAR, 1e-9)
        out.append(
            {
                "platform": platform,
                "design": design,
                "events_eligible": len(eligible),
                "events_moved": moved,
                "responsiveness": moved / len(eligible),
                "solo_moves": solo.get(key, 0),
                "solo_per_year": solo.get(key, 0) / years,
                "years_in_fleet": years,
                "instances": size.get(key, (0, None))[1],
            }
        )

    out.sort(key=lambda r: -r["responsiveness"])
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        for r in out:
            w.writerow(r)
    print(
        f"ranked designs={len(out)} fleet-wide events={len(fleetwide)}", file=sys.stderr
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
