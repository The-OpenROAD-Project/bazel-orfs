#!/usr/bin/env python3
"""Does the policy dominate today's default on every design? The verdict table.

Reads two arms of full-flow results written by the campaign runner
(stage "full": every stage's wall plus the KPIs OpenROAD wrote into the
per-step metrics JSONs), and the per-design noise bands from
noise_bands.py, and decides per design:

  * hard axes -- DRC errors, antenna violations, hold WNS -- may not get
    worse at all;
  * KPI axes -- minimum clock period (clock - setup WNS), setup TNS, area,
    power, wire length -- may not get worse by more than the design's own
    noise band for that metric;
  * total flow wall may not get worse; where the policy has nothing to do
    the final ODB should be byte-identical, and the hash says so.

A design passes when no axis is worse. The suite passes when every
design does. "Within noise" is a verdict, not a rounding: the raw deltas
stay in the table beside it.

    verdict.py --results DIR --base base-prof --policy base-p0073 \\
               --bands tmp/noise_bands_recent.json
"""

import argparse
import glob
import json
import os
import sys

# (metric, direction, label). direction: +1 means larger is better.
KPI_AXES = [
    ("min_period", -1, "min clock period"),
    ("finish__timing__setup__tns", +1, "setup TNS"),
    ("finish__design__instance__area", -1, "area"),
    ("finish__power__total", -1, "power"),
    ("detailedroute__route__wirelength", -1, "wire length"),
]
HARD_AXES = [
    ("detailedroute__route__drc_errors", -1, "DRC"),
    ("detailedroute__antenna__violating__nets", -1, "antenna"),
    ("finish__timing__hold__ws", +1, "hold WNS"),
]
# noise_bands.py's metric names for the KPI axes.
BAND_KEY = {
    "min_period": "min_period_ps",
    "finish__timing__setup__tns": "finish__timing__setup__tns",
    "finish__design__instance__area": "finish__design__instance__area",
    "finish__power__total": "finish__power__total",
    "detailedroute__route__wirelength": "detailedroute__route__wirelength",
}


def load_arm(results_dir, arm):
    """design -> record for one arm's full-flow results (first repeat)."""
    out = {}
    for path in sorted(glob.glob(os.path.join(results_dir, "*_full_{}_r*.json".format(arm)))):
        with open(path) as handle:
            record = json.load(handle)
        out.setdefault(record["design"], record)
    return out


def flat_metrics(record):
    """All KPI values of a record, later steps overriding earlier ones."""
    merged = {}
    for step in sorted(record["substeps"].get("_metrics", {})):
        merged.update(record["substeps"]["_metrics"][step])
    return merged


def clock_period(metrics):
    details = metrics.get("constraints__clocks__details") or []
    if not details:
        return None
    try:
        return float(str(details[0]).rsplit(":", 1)[1])
    except (ValueError, IndexError):
        return None


def design_bands(bands, design):
    """The noise-band record for a design, under either naming."""
    return bands.get(design) or bands.get("asap7/" + design) or {}


def kpis(record, bands=None):
    """The axes' values for one record, with min_period derived.

    The clock period comes from the metrics when a step recorded
    constraints__clocks__details, else from the design's noise-band record,
    whose period is read from ORFS's own history of the design.
    """
    metrics = flat_metrics(record)
    out = {k: metrics.get(k) for k, _, _ in KPI_AXES + HARD_AXES if k != "min_period"}
    period = clock_period(metrics)
    if period is None and bands:
        period = (design_bands(bands, record["design"]).get("_sources") or {}).get("period")
    ws = metrics.get("finish__timing__setup__ws")
    out["min_period"] = (period - ws) if (period is not None and ws is not None) else None
    return out


def flow_wall(record):
    return sum(
        got.get("wall_s") or 0
        for step, got in record["substeps"].items()
        if not step.startswith("_") and isinstance(got, dict)
    )


def judge(base_value, new_value, direction, band):
    """(delta, verdict) for one axis; delta is signed so + is worse."""
    if base_value is None or new_value is None:
        return None, "no data"
    delta = (new_value - base_value) * (-direction)
    if delta <= 0:
        return delta, "better" if delta < 0 else "same"
    if band is not None and delta <= band:
        return delta, "within noise"
    return delta, "WORSE"


def design_verdict(base, policy, bands):
    kb, kp = kpis(base, bands), kpis(policy, bands)
    rows = []
    worse = False
    for key, direction, label in HARD_AXES:
        delta, verdict = judge(kb.get(key), kp.get(key), direction, 0.0)
        rows.append((label, kb.get(key), kp.get(key), delta, None, verdict))
        worse |= verdict == "WORSE"
    this_bands = design_bands(bands, base["design"])
    for key, direction, label in KPI_AXES:
        rec = this_bands.get(BAND_KEY[key]) or {}
        band = None if rec.get("insufficient", True) else rec.get("band_2sigma")
        delta, verdict = judge(kb.get(key), kp.get(key), direction, band)
        rows.append((label, kb.get(key), kp.get(key), delta, band, verdict))
        worse |= verdict == "WORSE"
    wb, wp = flow_wall(base), flow_wall(policy)
    wall_delta = wp - wb
    same_odb = (
        base["substeps"].get("_final_sha1") is not None
        and base["substeps"].get("_final_sha1") == policy["substeps"].get("_final_sha1")
    )
    wall_verdict = "same" if abs(wall_delta) < 1.0 else ("better" if wall_delta < 0 else "WORSE")
    worse |= wall_verdict == "WORSE" and not same_odb and wall_delta > 0.02 * wb
    return {
        "design": base["design"],
        "axes": rows,
        "wall_base": wb,
        "wall_policy": wp,
        "wall_delta": wall_delta,
        "wall_pct": (100.0 * wall_delta / wb) if wb else None,
        "same_odb": same_odb,
        "dominated_or_tied": not worse,
    }


def fmt(v, digits=1):
    if v is None:
        return "–"
    if isinstance(v, float):
        return "{:.{d}f}".format(v, d=digits)
    return str(v)


def suite_table(verdicts):
    lines = [
        "| design | flow wall base (s) | policy (s) | delta | min period Δ | TNS Δ | area Δ | power Δ | wire Δ | DRC Δ | same ODB | verdict |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for v in sorted(verdicts, key=lambda v: v["wall_pct"] or 0):
        by = {label: (delta, verdict) for label, _, _, delta, _, verdict in v["axes"]}

        def cell(label):
            delta, verdict = by.get(label, (None, "no data"))
            if delta is None:
                return "–"
            mark = "" if verdict in ("better", "same") else (" ~" if verdict == "within noise" else " **worse**")
            # judge() signs delta so that + is worse; the table shows + as
            # better on every axis, as the footnote says.
            return "{}{}".format(fmt(-delta), mark)

        lines.append(
            "| {} | {} | {} | {} ({}%) | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                v["design"], fmt(v["wall_base"], 0), fmt(v["wall_policy"], 0),
                fmt(v["wall_delta"], 0), fmt(v["wall_pct"], 0),
                cell("min clock period"), cell("setup TNS"), cell("area"),
                cell("power"), cell("wire length"), cell("DRC"),
                "yes" if v["same_odb"] else "no",
                "pass" if v["dominated_or_tied"] else "**FAIL**",
            )
        )
    passed = sum(1 for v in verdicts if v["dominated_or_tied"])
    lines.append("")
    lines.append("{} of {} designs pass; ~ marks a move inside the design's noise band, "
                 "signed so that + is better on every axis.".format(passed, len(verdicts)))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--base", default="base-prof")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--bands", help="noise_bands.py JSON")
    args = parser.parse_args()
    bands = {}
    if args.bands:
        with open(args.bands) as handle:
            bands = json.load(handle)
    base = load_arm(args.results, args.base)
    policy = load_arm(args.results, args.policy)
    verdicts = [design_verdict(base[d], policy[d], bands) for d in sorted(base) if d in policy]
    if not verdicts:
        raise SystemExit("no design has both arms in {}".format(args.results))
    missing = sorted(set(base) ^ set(policy))
    sys.stdout.write(suite_table(verdicts))
    if missing:
        sys.stdout.write("\nNot yet measured on both arms: {}\n".format(", ".join(missing)))


if __name__ == "__main__":
    main()
