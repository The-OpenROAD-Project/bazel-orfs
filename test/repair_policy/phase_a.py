#!/usr/bin/env python3
"""Phase A of the repair-knobs campaign: every policy against the rows-only control.

One row per vehicle and stage; one column per arm: the setup-repair call's
median wall over the repeats with its delta against the control, and the
final WNS and TNS deltas in picoseconds, + is better. The control is the
two row fixes with no policy (arm `base-p00670068`, falling back to the
inert move budget's arm `base-p0072`, which measured identical to it),
so a policy's wall effect is separated from OpenROAD #11387's.

Read the rows as flow-level, not stage-level: a patched binary rebuilds
the earlier stages too, and the place stage runs repair_timing, so a
policy arm's cts and grt inputs are its own, not the control's. The
first progress row of each run records the starting WNS, TNS and
violating-endpoint count that show it. The judgment is the full flow,
which is what Phase B runs; this table says where along the flow the
policy's effect shows up.

    phase_a.py --results DIR [--arms base-p0069 base-p0070 ...]
"""

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "repair_timing_runtime"))
import report  # noqa: E402

STAGES = ("floorplan", "cts", "grt")
STEP = {"floorplan": "2_1_floorplan", "cts": "4_1_cts", "grt": "5_1_grt"}
DEFAULT_ARMS = ["base-p0069", "base-p0070", "base-p0071", "base-p0072", "base-p0073", "base-p0074"]


def samples(records, design, stage, arm):
    """[(setup_s, final wns, final tns)] for one arm's repeats."""
    out = []
    for r in records:
        if r["design"] != design or r["stage"] != stage or r["arm"] != arm:
            continue
        got = r["substeps"].get(STEP[stage])
        if not got:
            continue
        for index, call in enumerate(got.get("repair", [])):
            if call["kind"] not in ("setup_hold", "floorplan_setup"):
                continue
            final = report.final_row(r, STEP[stage], index) or {}
            out.append((call["setup_s"], final.get("wns"), final.get("en_tns")))
    return out


def control_arm(records, design, stage):
    for arm in ("base-p00670068", "base-p0072"):
        if samples(records, design, stage, arm):
            return arm
    return None


def med(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def rows(records, arms, designs=None):
    out = []
    designs = designs or sorted({r["design"] for r in records if r["arm"] in arms})
    for design in designs:
        for stage in STAGES:
            control = control_arm(records, design, stage)
            if not control:
                continue
            c = samples(records, design, stage, control)
            c_s, c_wns, c_tns = med(s[0] for s in c), med(s[1] for s in c), med(s[2] for s in c)
            cells = {}
            for arm in arms:
                p = samples(records, design, stage, arm)
                if not p:
                    cells[arm] = None
                    continue
                p_s = med(s[0] for s in p)
                cells[arm] = {
                    "wall": p_s,
                    "pct": 100.0 * (p_s - c_s) / c_s if c_s else None,
                    "sigma2": report.two_sigma([s[0] for s in p]),
                    "wns": (med(s[1] for s in p) - c_wns) if c_wns is not None else None,
                    "tns": (med(s[2] for s in p) - c_tns) if c_tns is not None else None,
                    "n": len(p),
                }
            out.append({"design": design, "stage": stage, "control": control,
                        "control_wall": c_s, "control_sigma2": report.two_sigma([s[0] for s in c]),
                        "control_wns": c_wns, "cells": cells})
    return out


def table(rows_, arms):
    lines = ["| design | stage | control (s, 2σ, WNS ps) | " + " | ".join(a.replace("base-p", "") for a in arms) + " |",
             "| --- | --- | --- | " + " | ".join("---" for _ in arms) + " |"]
    for r in rows_:
        cells = []
        for arm in arms:
            c = r["cells"].get(arm)
            if not c:
                cells.append("–")
                continue
            cells.append("{:.0f} s ({:+.0f}%, 2σ {:.1f}), WNS {:+.1f}, TNS {:+.0f}".format(
                c["wall"], c["pct"], c["sigma2"], c["wns"] or 0.0, c["tns"] or 0.0))
        lines.append("| {} | {} | {:.0f}, {:.1f}, {:.1f} | ".format(
            r["design"], r["stage"], r["control_wall"], r["control_sigma2"], r["control_wns"] or 0.0) + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--arms", nargs="+", default=DEFAULT_ARMS)
    parser.add_argument("--designs", nargs="*")
    args = parser.parse_args()
    records = report.load_results(args.results)
    sys.stdout.write(table(rows(records, args.arms, args.designs), args.arms))


if __name__ == "__main__":
    main()
