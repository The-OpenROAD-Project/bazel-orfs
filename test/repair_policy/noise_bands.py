#!/usr/bin/env python3
"""Derive per-design, per-metric noise bands from ORFS's own KPI history.

For every ORFS design directory ``flow/designs/<platform>/<design>/`` two
files carry the history of the design's key performance indicators:

1. ``metadata-base-ok.json`` -- a flat dict of metric -> measured value,
   committed until it was deleted on 2025-02-27 (commit 2152d38ab).  Its
   values are the unpadded ("golden") measurements and are taken as-is.  It
   also carries the clock period in ``constraints__clocks__details``.

2. ``rules-base.json`` -- still present.  Each entry is
   ``{"value": v, "compare": op}`` where ``v`` is a *padded* threshold that
   ``flow/util/genRuleFile.py`` derived from the golden value with fixed
   transforms, which this module inverts:

   * ``padding`` (area, wirelength; 15%): ``v = round(g * 1.15)`` so
     ``g ~ v / 1.15``.
   * ``direct`` (drc_errors): ``v = g``.
   * ``period_padding`` (ws 5%, tns 20%): with ``neg = min(g, 0)``,
     ``v = neg - max(neg*p/100, period*p/100) = neg - period*p/100``.
     Hence ``g = v + period*p/100`` when that is negative; when it is
     ``>= 0`` the golden was non-negative and is not recoverable -- it is
     recorded as the string ``"met"`` and dropped from the numeric series.

   The period is not in ``rules-base.json``; it is taken from the newest
   ``metadata-base-ok.json`` dated at or before the rules commit (else the
   newest overall, else ``set clk_period``/``create_clock -period`` in the
   design's ``constraint.sdc``).

Per design and metric the two sources are merged into one (date, value)
series sorted by commit date; a least-squares line over the commit index
is removed and the noise band is 2 * population standard deviation of the
residuals.  The derived axis ``min_period_ps = period - ws`` is reported in
whatever unit the design's files use (ps for asap7, ns for sky130hd).

Only ``git log``/``git show`` are used on the ORFS clone; it is never
checked out or modified.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys

PADDED_PCT = {
    "finish__design__instance__area": 15.0,
    "detailedroute__route__wirelength": 15.0,
}
DIRECT = {"detailedroute__route__drc_errors"}
PERIOD_PADDED_PCT = {
    "finish__timing__setup__ws": 5.0,
    "finish__timing__setup__tns": 20.0,
}
METADATA_METRICS = [
    "finish__timing__setup__ws",
    "finish__timing__setup__tns",
    "finish__design__instance__area",
    "finish__power__total",
    "detailedroute__route__wirelength",
    "detailedroute__route__drc_errors",
]
DELETED_METADATA_SHA = "2152d38ab"


# ---------------------------------------------------------------- pure math


def invert_padding(value, pct):
    """Golden value behind a ``padding`` threshold (value = round(g*(1+p)))."""
    return float(value) / (1.0 + pct / 100.0)


def invert_period_padding(value, period, pct):
    """Golden value behind a ``period_padding`` threshold, or ``"met"``.

    value = min(g, 0) - period*pct/100, so g = value + period*pct/100 when
    negative; a non-negative result means g >= 0 and is unrecoverable.
    """
    golden = float(value) + float(period) * pct / 100.0
    if golden >= 0:
        return "met"
    return golden


def depad_rules(rules, period):
    """Map a rules-base.json dict to {metric: golden} for the known metrics."""
    out = {}
    for metric, pct in PADDED_PCT.items():
        if metric in rules:
            out[metric] = invert_padding(rules[metric]["value"], pct)
    for metric in DIRECT:
        if metric in rules:
            out[metric] = to_number(rules[metric]["value"])
    if period is not None:
        for metric, pct in PERIOD_PADDED_PCT.items():
            if metric in rules:
                out[metric] = invert_period_padding(
                    rules[metric]["value"], period, pct
                )
    return out


def to_number(value):
    """Return value as float, or None when it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def period_from_metadata(meta):
    """Clock period from constraints__clocks__details ("name: 1300.0")."""
    details = meta.get("constraints__clocks__details") or []
    if not details:
        return None
    first = details[0]
    if ": " not in first:
        return None
    return to_number(first.split(": ", 1)[1])


def period_from_sdc(text):
    """Best-effort period from an SDC: literal -period or set clk_period."""
    m = re.search(r"create_clock[^\n]*-period\s+([0-9.]+)", text)
    if m is None:
        m = re.search(r"^\s*set\s+clk_period\s+([0-9.]+)", text, re.M)
    return to_number(m.group(1)) if m else None


def merge_series(*sources):
    """Merge (date, value) lists, drop non-numeric values, sort by date."""
    points = []
    for src in sources:
        for date, value in src:
            num = to_number(value)
            if num is not None and math.isfinite(num):
                points.append((date, num))
    points.sort(key=lambda p: p[0])
    return points


def linear_trend(values):
    """Least-squares slope/intercept over index 0..n-1, and residuals."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, []
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / sxx if sxx else 0.0
    intercept = my - slope * mx
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, values)]
    return slope, intercept, residuals


def pstdev(values):
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def summarize(points, unit_note=""):
    """Compute the noise-band record for a sorted (date, value) series."""
    values = [v for _, v in points]
    n = len(values)
    insufficient = n < 3
    _, _, residuals = linear_trend(values)
    steps = [abs(b - a) for a, b in zip(values, values[1:])]
    return {
        "n": n,
        "first_date": points[0][0] if points else None,
        "last_date": points[-1][0] if points else None,
        "last": values[-1] if values else None,
        "band_2sigma": 0.0 if insufficient else 2.0 * pstdev(residuals),
        "max_step": max(steps) if steps else 0.0,
        "unit_note": unit_note,
        "insufficient": insufficient,
    }


def band(results, design, metric):
    """2-sigma noise band for results[design][metric], or None if absent."""
    rec = results.get(design, {}).get(metric)
    if rec is None or rec.get("insufficient"):
        return None
    return rec["band_2sigma"]


# ---------------------------------------------------------------------- git


def git(orfs, *args):
    return subprocess.run(
        ["git", "-C", orfs] + list(args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        universal_newlines=True,
    ).stdout


def file_history(orfs, path):
    """[(sha, date, parsed_json)] for every commit touching path, oldest last."""
    out = []
    log = git(orfs, "log", "--follow", "--format=%H:%cs", "--", path)
    for line in log.splitlines():
        sha, date = line.split(":", 1)
        try:
            text = git(orfs, "show", "%s:%s" % (sha, path))
        except subprocess.CalledProcessError:
            continue  # the deleting commit has no blob
        try:
            out.append((sha, date, json.loads(text)))
        except ValueError:
            continue
    return out


def window(points, since=None, last=None):
    """Restrict a sorted (date, value) series to a recent window.

    The whole history is an era, not a noise floor: sky130hd/aes's area
    moved 9x between 2021 and today. A band that should say "would a
    maintainer notice this move" is taken over the recent history only,
    by date (`since`, ISO) or by count (`last` points), whichever is
    given; both apply if both are.
    """
    out = points
    if since:
        out = [(d, v) for d, v in out if d >= since]
    if last:
        out = out[-last:]
    return out


def load_design(orfs, design, since=None, last=None):
    """Return the results dict for one "<platform>/<design>"."""
    base = "flow/designs/%s" % design
    meta_hist = file_history(orfs, base + "/metadata-base-ok.json")
    rules_hist = file_history(orfs, base + "/rules-base.json")

    periods = sorted(
        (d, period_from_metadata(m))
        for _, d, m in meta_hist
        if period_from_metadata(m) is not None
    )
    sdc_period = None
    sdc = os.path.join(orfs, base, "constraint.sdc")
    if os.path.exists(sdc):
        with open(sdc) as f:
            sdc_period = period_from_sdc(f.read())

    def period_at(date):
        before = [p for d, p in periods if d <= date]
        if before:
            return before[-1]
        if periods:
            return periods[0][1]
        return sdc_period

    series = {m: [] for m in METADATA_METRICS}
    series["min_period_ps"] = []
    contributed = {"metadata": 0, "rules": 0}
    for _, date, meta in meta_hist:
        period = period_from_metadata(meta)
        for m in METADATA_METRICS:
            if m in meta:
                series[m].append((date, meta[m]))
                contributed["metadata"] += 1
        ws = to_number(meta.get("finish__timing__setup__ws"))
        if period is not None and ws is not None:
            series["min_period_ps"].append((date, period - ws))
    for _, date, rules in rules_hist:
        period = period_at(date)
        golden = depad_rules(rules, period)
        for m, v in golden.items():
            series[m].append((date, v))
            contributed["rules"] += 1
        ws = golden.get("finish__timing__setup__ws")
        if period is not None and isinstance(ws, float):
            series["min_period_ps"].append((date, period - ws))

    unit = "ps" if design.startswith("asap7") else "file units (ns for sky130hd)"
    results = {}
    for m, pts in series.items():
        merged = window(merge_series(pts), since, last)
        note = unit if ("timing" in m or m == "min_period_ps") else ""
        if m == "min_period_ps" and period_at("9999-12-31") is None:
            note = "period unknown; timing metrics skipped"
        results[m] = summarize(merged, note)
    results["_sources"] = {
        "metadata_commits": len(meta_hist),
        "rules_commits": len(rules_hist),
        "metadata_points": contributed["metadata"],
        "rules_points": contributed["rules"],
        "period": period_at("9999-12-31"),
    }
    return results


def enumerate_designs(orfs, platforms):
    designs = []
    for plat in platforms:
        root = os.path.join(orfs, "flow", "designs", plat)
        for name in sorted(os.listdir(root)):
            if os.path.exists(os.path.join(root, name, "rules-base.json")):
                designs.append("%s/%s" % (plat, name))
    return designs


def summary_line(design, res):
    src = res["_sources"]
    parts = []
    for m in METADATA_METRICS + ["min_period_ps"]:
        r = res[m]
        tag = "n=%d" % r["n"]
        if r["insufficient"]:
            tag += " insufficient"
        else:
            tag += " band=%.4g step=%.4g" % (r["band_2sigma"], r["max_step"])
        parts.append("%s[%s]" % (m.split("__")[-1], tag))
    return "%s: meta=%d rules=%d period=%s | %s" % (
        design,
        src["metadata_commits"],
        src["rules_commits"],
        src["period"],
        " ".join(parts),
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--orfs", required=True, help="path to ORFS clone")
    ap.add_argument("--designs", nargs="*", default=[], help="platform/design")
    ap.add_argument("--platforms", nargs="*", default=[], help="enumerate")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    ap.add_argument("--since", help="ISO date; keep only points from then on")
    ap.add_argument("--last", type=int, help="keep only the last N points")
    args = ap.parse_args(argv)

    designs = list(args.designs) + enumerate_designs(args.orfs, args.platforms)
    if not designs:
        ap.error("give --designs and/or --platforms")
    results = {}
    for design in designs:
        results[design] = load_design(args.orfs, design, args.since, args.last)
        print(summary_line(design, results[design]), file=sys.stderr)
    text = json.dumps(results, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
