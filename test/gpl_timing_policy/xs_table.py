#!/usr/bin/env python3
"""One row per XiangShan study run: reg2reg min period at grt, stage times.

Usage: xs_table.py BAZEL_BIN_XS_DIR BLOCK [BLOCK ...]
Reads <dir>/<block>_<run>_kpi.txt and <dir>/logs/asap7/<block>/<run>/*.log;
prints a table and, per arm, the mean and spread over seeds.
"""
import os
import re
import statistics
import sys

ARMS = ["tdbase", "tdoff", "tdvirt", "tdsta", "tdfast", "tdhyb"]
SEEDS = ["1", "2", "3"]
STAGES = [
    ("gpl", "3_3_place_gp.log"),
    ("resz", "3_4_place_resized.log"),
    ("cts", "4_1_cts.log"),
    ("grt", "5_1_grt.log"),
]
ELAPSED = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):([\d.]+)")
STAMP = re.compile(r"^\[\s*([0-9.]+)\]")


def elapsed(path):
    """Seconds from the closing Elapsed line, else the last timestamp."""
    if not os.path.exists(path):
        return None
    last = None
    secs = None
    with open(path, errors="replace") as f:
        for line in f:
            m = ELAPSED.search(line)
            if m:
                h, mi, s = m.groups()
                secs = int(h or 0) * 3600 + int(mi) * 60 + float(s)
            t = STAMP.match(line)
            if t:
                last = float(t.group(1))
    return secs if secs is not None else last


def reweights(path):
    if not os.path.exists(path):
        return None
    total = 0.0
    with open(path, errors="replace") as f:
        for line in f:
            m = re.search(r"GPL-9911\] Timing-driven slacks from \w+: ([\d.]+) s", line)
            if m:
                total += float(m.group(1))
    return total


def period(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            m = re.match(r"reg2reg min period (-?[\d.]+) ps", line)
            if m:
                return float(m.group(1))
    return None


def fmt(v, w=6, p=0):
    return f"{v:{w}.{p}f}" if v is not None else " " * (w - 1) + "-"


def main():
    d = sys.argv[1]
    for block in sys.argv[2:]:
        print(f"\n{block}: reg2reg min period at grt (ps), stage wall (s)")
        print(f"  {'run':10} {'period':>7} {'gpl':>6} {'td':>6} {'resz':>6} {'cts':>6} {'grt':>6}")
        per_arm = {}
        for arm in ARMS:
            for seed in SEEDS:
                run = f"{arm}s{seed}"
                logs = os.path.join(d, "logs/asap7", block, run)
                p = period(os.path.join(os.environ.get("KPI_DIR", d), f"{block}_{run}_kpi.txt"))
                times = [elapsed(os.path.join(logs, f)) for _, f in STAGES]
                td = reweights(os.path.join(logs, "3_3_place_gp.log"))
                per_arm.setdefault(arm, []).append((p, times[0], td, times[1], times[2], times[3]))
                print(
                    f"  {run:10} {fmt(p, 7)} "
                    + " ".join(fmt(t) for t in [times[0], td] + times[1:])
                )
        print(f"  {'arm':10} {'period mean (min..max)':>24}   mean s: gpl     td   resz    cts    grt  place..grt")
        for arm, rows in per_arm.items():
            ps = [r[0] for r in rows if r[0] is not None]
            def m(i):
                v = [r[i] for r in rows if r[i] is not None]
                return statistics.mean(v) if v else None
            tot = [sum(r[i] for i in (1, 3, 4, 5)) for r in rows if None not in (r[1], r[3], r[4], r[5])]
            print(
                f"  {arm:10} {statistics.mean(ps):8.0f} ({min(ps):.0f}..{max(ps):.0f})          "
                + " ".join(fmt(m(i)) for i in (1, 2, 3, 4, 5))
                + f" {fmt(statistics.mean(tot) if tot else None, 10)}"
            )


if __name__ == "__main__":
    main()
