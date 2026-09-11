#!/usr/bin/env python3
"""The oracle: the best knob setting a perfect user would have picked, per design.

For every (design, stage) with knob arms recorded, the fastest arm whose
final WNS is within `wns_tol` ps of the profiled base and whose final TNS
is not worse. That is what a design owner who ran every setting and read
the log would write into config.mk. The policy has to match or beat it
where it exists, and lose nowhere it does not.

    oracle.py --results DIR [--wns-tol 0.5]
"""

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "repair_timing_runtime"))
import report  # noqa: E402


def oracle_rows(records, wns_tol=0.5, base="base-prof", suffix="-prof"):
    rows = []
    pairs = sorted({(r["design"], r["stage"]) for r in records if r["stage"] in ("cts", "grt")})
    for design, stage in pairs:
        samples = report.arm_samples(records, design, stage)
        if base not in samples:
            continue

        def med(arm, index):
            values = [s[index] for s in samples[arm] if s[index] is not None]
            return statistics.median(values) if values else None

        base_s, base_wns, base_tns = med(base, 0), med(base, 1), med(base, 3)
        best = (base, base_s, 0.0, 0.0)
        for arm in samples:
            if arm == base or not arm.endswith(suffix):
                continue
            secs, wns, tns = med(arm, 0), med(arm, 1), med(arm, 3)
            if secs is None or wns is None or tns is None or base_wns is None or base_tns is None:
                continue
            if wns >= base_wns - wns_tol and tns >= base_tns and secs < best[1]:
                best = (arm, secs, wns - base_wns, tns - base_tns)
        rows.append({
            "design": design, "stage": stage, "base_s": base_s,
            "oracle": best[0], "oracle_s": best[1],
            "saving_pct": 100.0 * (base_s - best[1]) / base_s if base_s else 0.0,
            "wns_delta": best[2], "tns_delta": best[3],
        })
    return rows


def oracle_table(rows):
    lines = [
        "| design | stage | base (s) | oracle arm | oracle (s) | saving | WNS Δ (ps) | TNS Δ (ps) |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append("| {} | {} | {:.1f} | {} | {:.1f} | {:.0f}% | {:.1f} | {:.0f} |".format(
            r["design"], r["stage"], r["base_s"], r["oracle"], r["oracle_s"],
            r["saving_pct"], r["wns_delta"], r["tns_delta"]))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--wns-tol", type=float, default=0.5)
    args = parser.parse_args()
    sys.stdout.write(oracle_table(oracle_rows(report.load_results(args.results), args.wns_tol)))


if __name__ == "__main__":
    main()
