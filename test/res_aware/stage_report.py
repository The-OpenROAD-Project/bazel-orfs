#!/usr/bin/env python3
"""Minimum clock period across a flow's stages, per arm, as ASCII art.

Each stage's metrics JSON (logs/<platform>/<design>/<variant>/*.json)
carries its worst setup slack, `<stage>__timing__setup__ws`. With the
clock at `--period`, the minimum period the stage would close at is the
period less that slack. One bar per stage and arm, on one scale, so a
change that pays at one stage and not another shows where it pays.

    stage_report.py --period 473 A0=<logs-dir> A1=<logs-dir> ...
"""

import argparse
import json
import os
import sys

# The stages that report timing, in flow order: (json file, metric prefix)
STAGES = [
    ("2_1_floorplan.json", "floorplan", "floorplan"),
    ("3_3_place_gp.json", "globalplace", "global place"),
    ("3_4_place_resized.json", "placeopt", "place repair"),
    ("3_5_place_dp.json", "detailedplace", "detailed place"),
    ("4_1_cts.json", "cts", "cts"),
    ("5_1_grt.json", "globalroute", "global route"),
    ("6_report.json", "finish", "final"),
]


def read_arm(logs_dir):
    """{stage label: worst slack in ps} for the stages that ran."""
    out = {}
    for name, prefix, label in STAGES:
        path = os.path.join(logs_dir, name)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            metrics = json.load(f)
        key = prefix + "__timing__setup__ws"
        if key not in metrics:
            raise SystemExit(f"{path}: no {key}")
        out[label] = float(metrics[key])
    if not out:
        raise SystemExit(f"{logs_dir}: no stage metrics")
    return out


def render(period, arms, width=48):
    rows = []
    for label in [s[2] for s in STAGES]:
        for arm, slacks in arms:
            if label in slacks:
                rows.append((label, arm, period - slacks[label]))
    top = max(p for _, _, p in rows)
    name_w = max(len(a) for a, _ in arms)
    lines = [
        f"minimum clock period across stages (clock {period:g} ps, "
        f"period = clock - worst slack)",
        "",
    ]
    previous = None
    for label, arm, p in rows:
        stage = label if label != previous else ""
        previous = label
        bar = "#" * max(1, round(width * p / top))
        lines.append(f"{stage:>14} {arm:<{name_w}} |{bar:<{width}}| {p:7.1f} ps")
    lines.append(f"{'':>14} {'':<{name_w}} 0{'':{width - 1}}{top:.0f} ps")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--period", type=float, required=True, help="clock in ps")
    ap.add_argument("arms", nargs="+", help="NAME=logs-dir")
    args = ap.parse_args(argv)
    arms = []
    for spec in args.arms:
        name, sep, path = spec.partition("=")
        if not sep:
            raise SystemExit(f"{spec}: expected NAME=logs-dir")
        arms.append((name, read_arm(path)))
    print(render(args.period, arms))


if __name__ == "__main__":
    main(sys.argv[1:])
