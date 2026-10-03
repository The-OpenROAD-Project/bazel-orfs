#!/usr/bin/env python3
"""The wire campaign's ledger: rows in, a table and the next density out.

    campaign.py add --results results.json --arm A0 --density 0.2 --seed 1 row.json
    campaign.py table --results results.json
    campaign.py next --results results.json

A row is one wire_probe.tcl JSON, keyed by (arm, density, seed). `add`
replaces a row with the same key, so re-running a point after a fix
leaves one row, and a campaign stopped on one machine resumes on another
from the committed results.json.

`next` says where to sample. Each arm starts at the two ends, 0.2 and
0.7. Between two sampled densities the period is unknown, and the
interval to split is the one whose ends differ the most; a difference
the seeds cannot resolve is no reason to sample (docs/plans/
xstile-wire-campaign.md, "Phase 2"). It stops when no interval wider
than MIN_STEP has ends that differ by more than the noise: the rough
picture, enough to decide what to spend time on next.
"""

import argparse
import json
import statistics
import sys

ENDS = (0.2, 0.7)
MIN_STEP = 0.1
# The noise floor until an arm has seeds of its own: the place stage's 2
# sigma over twelve seeds in docs/studies/pre-route-pessimism, 4.3 %.
DEFAULT_NOISE = 0.043


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"rows": []}


def save(path, ledger):
    ledger["rows"].sort(key=lambda r: (r["arm"], r["density"], r["seed"]))
    with open(path, "w") as f:
        json.dump(ledger, f, indent=2, sort_keys=True)
        f.write("\n")


def add(ledger, arm, density, seed, row):
    key = (arm, density, seed)
    ledger["rows"] = [
        r for r in ledger["rows"] if (r["arm"], r["density"], r["seed"]) != key
    ]
    ledger["rows"].append(dict(row, arm=arm, density=density, seed=seed))


def points(ledger, arm):
    """{density: [period_ps, ...]} for one arm."""
    out = {}
    for r in ledger["rows"]:
        if r["arm"] == arm:
            out.setdefault(r["density"], []).append(r["period_ps"])
    return out


def noise(pts):
    """Relative 2-sigma of the seeds, pooled over densities with more than
    one, or the default until there are any."""
    spreads = [
        2 * statistics.stdev(v) / statistics.mean(v) for v in pts.values() if len(v) > 1
    ]
    return max(spreads) if spreads else DEFAULT_NOISE


def next_densities(ledger, arm):
    """The densities to sample next for one arm, most informative first;
    empty when the rough picture is in."""
    pts = points(ledger, arm)
    missing = [d for d in ENDS if d not in pts]
    if missing:
        return missing
    rel = noise(pts)
    ds = sorted(pts)
    candidates = []
    for lo, hi in zip(ds, ds[1:]):
        if hi - lo <= MIN_STEP + 1e-9:
            continue
        a, b = statistics.mean(pts[lo]), statistics.mean(pts[hi])
        diff = abs(a - b) / min(a, b)
        if diff <= rel:
            continue
        mid = round((lo + hi) / 2 / 0.05) * 0.05
        candidates.append((diff * (hi - lo), round(mid, 2)))
    return [mid for _, mid in sorted(candidates, reverse=True)]


def table(ledger):
    lines = [
        "| arm | density | seeds | period ps | floor ps | wire share | HPWL m |"
        " worst path wire um | congestion | place peak GiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    groups = {}
    for r in ledger["rows"]:
        groups.setdefault((r["arm"], r["density"]), []).append(r)
    for (arm, density), rows in sorted(groups.items()):
        periods = [r["period_ps"] for r in rows]
        period = statistics.mean(periods)
        floor = statistics.mean(r["floor_ps"] for r in rows)
        span = " (%.0f-%.0f)" % (min(periods), max(periods)) if len(periods) > 1 else ""
        # the place stage's peak: global placement is 3_3, or 3_1 when
        # both driven modes are off
        peaks = [s["peak_gib"] for r in rows for s in r.get("steps", {}).values()]
        congestion = [
            r["rudy_top2_congestion"]
            for r in rows
            if r.get("rudy_top2_congestion") is not None
        ]
        lines.append(
            "| %s | %.2f | %d | %.0f%s | %.0f | %.0f %% | %.4g | %.0f | %s | %s |"
            % (
                arm,
                density,
                len(rows),
                period,
                span,
                floor,
                100 * (period - floor) / period,
                statistics.mean(r["hpwl_m"] for r in rows),
                statistics.mean(r["worst_wire_um"] for r in rows),
                "%.3f" % statistics.mean(congestion) if congestion else "",
                "%.1f" % max(peaks) if peaks else "",
            )
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("--results", required=True)
    p_add.add_argument("--arm", required=True)
    p_add.add_argument("--density", type=float, required=True)
    p_add.add_argument("--seed", type=int, default=0)
    p_add.add_argument("row")
    for name in ("table", "next"):
        p = sub.add_parser(name)
        p.add_argument("--results", required=True)
    args = parser.parse_args(argv)
    ledger = load(args.results)
    if args.cmd == "add":
        with open(args.row) as f:
            add(ledger, args.arm, args.density, args.seed, json.load(f))
        save(args.results, ledger)
    elif args.cmd == "table":
        print(table(ledger))
    else:
        arms = sorted({r["arm"] for r in ledger["rows"]})
        for arm in arms:
            nxt = next_densities(ledger, arm)
            print("%s: %s" % (arm, " ".join("%.2f" % d for d in nxt) or "done"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
