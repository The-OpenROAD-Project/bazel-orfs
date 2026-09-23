#!/usr/bin/env python3
"""One markdown table from a results directory of grt_bench.py cells.

    report.py results_dir/ [--baseline baseline]

Rows are (design, arm); columns the numbers a decision needs: status,
wall, pin_access, global_route, FastRoute's monotonic and overflow
iteration phases, peak RSS, wirelength, and each against the baseline arm
of the same design.
"""

import argparse
import glob
import json
import os
import sys


def load(results_dir):
    cells = []
    for p in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        if p.endswith(".metrics.json"):
            continue
        with open(p) as f:
            try:
                cells.append(json.load(f))
            except ValueError:
                continue
    return [c for c in cells if "design" in c and "arm" in c]


def fmt(v, unit=""):
    if v is None or v == "":
        return "-"
    if isinstance(v, (int, float)):
        if abs(v) >= 100:
            return "%.0f%s" % (v, unit)
        return "%.1f%s" % (v, unit)
    return str(v)


def ratio(v, base):
    try:
        return "%.2fx" % (float(base) / float(v)) if v and base else "-"
    except (TypeError, ValueError, ZeroDivisionError):
        return "-"


def table(cells, baseline):
    by = {}
    for c in cells:
        by.setdefault((c["design"], c["arm"]), []).append(c)
    rows = []
    for (design, arm), reps in sorted(by.items()):
        # median over repeats of the numeric fields
        def med(key):
            vals = sorted(
                float(c[key]) for c in reps if isinstance(c.get(key), (int, float))
            )
            return vals[len(vals) // 2] if vals else None

        rows.append(
            {
                "design": design,
                "arm": arm,
                "status": ",".join(sorted(set(c.get("status", "?") for c in reps))),
                "wall_s": med("wall_s"),
                "pin_access_s": med("pin_access_s"),
                "global_route_s": med("global_route_s"),
                "monotonic_s": med("fastroute__monotonic_s"),
                "overflow_iterations_s": med("fastroute__overflow_iterations_s"),
                "vm_hwm_gb": (
                    (med("vm_hwm_kb") or 0) / 1048576.0 if med("vm_hwm_kb") else None
                ),
                "wirelength_um": med("wirelength"),
            }
        )
    base = {r["design"]: r for r in rows if r["arm"] == baseline}
    out = [
        "| design | arm | status | wall s | pin_access s | global_route s | vs base | monotonic s | overflow iters s | peak GB | wirelength um |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        b = base.get(r["design"], {})
        out.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["design"],
                r["arm"],
                r["status"],
                fmt(r["wall_s"]),
                fmt(r["pin_access_s"]),
                fmt(r["global_route_s"]),
                ratio(r["global_route_s"], b.get("global_route_s")),
                fmt(r["monotonic_s"]),
                fmt(r["overflow_iterations_s"]),
                fmt(r["vm_hwm_gb"]),
                fmt(r["wirelength_um"]),
            )
        )
    return "\n".join(out)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results_dir")
    ap.add_argument("--baseline", default="baseline")
    a = ap.parse_args(argv[1:])
    cells = load(a.results_dir)
    if not cells:
        print("no results in", a.results_dir)
        return 1
    print(table(cells, a.baseline))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
