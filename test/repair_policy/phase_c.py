#!/usr/bin/env python3
"""Phase C: the designs that moved, three repeats each, with a 2σ.

Per mover and arm: median flow wall over the repeats with its 2σ, the
median minimum clock period and TNS deltas against the default's
medians, and whether the difference resolves (outside 2σ·sqrt(2/k) of
the default's repeats). The verdict tables judge one run; this table
says which of those judgments a repeat would have changed.

    phase_c.py --results DIR --bands JSON [--policies base-p0074 base-p0069 base-p0077]
"""

import argparse
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "repair_timing_runtime"))
import report  # noqa: E402
import verdict  # noqa: E402


def load_all(results_dir, arm):
    out = {}
    for path in sorted(glob.glob(os.path.join(results_dir, "*_full_{}_r*.json".format(arm)))):
        with open(path) as handle:
            rec = json.load(handle)
        out.setdefault(rec["design"], []).append(rec)
    return out


def med(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def rows(results_dir, bands, base, policies):
    base_all = load_all(results_dir, base)
    out = []
    for policy in policies:
        pol_all = load_all(results_dir, policy)
        for design in sorted(pol_all):
            b, p = base_all.get(design, []), pol_all[design]
            if len(p) < 2 or len(b) < 2:
                continue
            bw = [verdict.flow_wall(r) for r in b]
            pw = [verdict.flow_wall(r) for r in p]
            bk = [verdict.kpis(r, bands) for r in b]
            pk = [verdict.kpis(r, bands) for r in p]
            sigma2 = report.two_sigma(bw)
            res = report.resolution(sigma2, min(len(bw), len(pw)))
            delta = med(pw) - med(bw)
            out.append({
                "policy": policy.replace("base-", ""), "design": design,
                "n": (len(b), len(p)), "base_wall": med(bw), "policy_wall": med(pw),
                "delta": delta, "sigma2": sigma2, "resolution": res,
                "verdict": "did not resolve" if abs(delta) <= res else ("faster" if delta < 0 else "slower"),
                "min_period": (med(k["min_period"] for k in bk) or 0) - (med(k["min_period"] for k in pk) or 0),
                "tns": (med(k["finish__timing__setup__tns"] for k in pk) or 0) - (med(k["finish__timing__setup__tns"] for k in bk) or 0),
                "walls": (bw, pw),
            })
    return out


def table(rows_):
    lines = ["| policy | design | default wall (s), repeats | policy wall (s), repeats | delta | 2σ (default) | resolution | verdict | min period Δ (ps, + better) | TNS Δ (ps, + better) |",
             "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |"]
    for r in rows_:
        lines.append("| {} | {} | {} | {} | {:+.0f} ({:+.0f}%) | {:.0f} | {:.0f} | {} | {:+.1f} | {:+.0f} |".format(
            r["policy"], r["design"],
            ", ".join("{:.0f}".format(w) for w in r["walls"][0]), ", ".join("{:.0f}".format(w) for w in r["walls"][1]),
            r["delta"], 100 * r["delta"] / r["base_wall"], r["sigma2"], r["resolution"], r["verdict"],
            r["min_period"], r["tns"]))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--bands", required=True)
    ap.add_argument("--base", default="base-p00670068")
    ap.add_argument("--policies", nargs="+", default=["base-p0074", "base-p0069", "base-p0077"])
    args = ap.parse_args()
    with open(args.bands) as handle:
        bands = json.load(handle)
    sys.stdout.write(table(rows(args.results, bands, args.base, args.policies)))


if __name__ == "__main__":
    main()
