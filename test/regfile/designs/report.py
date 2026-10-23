"""The arms' measurements as tables: QoR against flip-flops, and stage times.

    report.py --csv out.csv --md out.md <files...>

The files are each arm's <arm>.json and <arm>_power.json from measure.tcl
and the logs of its stages; an arm is named <design>_<shape>_<period> and
a log belongs to the arm whose name is in its path. An arm with no
measurement shows as not yet measured.
"""

import argparse
import collections
import json
import os
import re

STAGES = (
    ("synth", ("1_",)),
    ("floorplan", ("2_",)),
    ("place", ("3_",)),
    ("cts", ("4_",)),
    ("grt", ("5_1_",)),
    ("route", ("5_2_", "5_3_")),
)
ELAPSED = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\[h:\]min:sec")


def seconds(text):
    total = 0.0
    for h, m, s in ELAPSED.findall(text):
        total += (int(h) if h else 0) * 3600 + int(m) * 60 + float(s)
    return total


def total_power(power):
    """report_power -format json: the design's total, in W."""
    for key in ("total", "Total"):
        if key in power:
            value = power[key]
            return value["total"] if isinstance(value, dict) else value
    raise ValueError("no total in report_power's JSON: %s" % sorted(power))


def load_power(text):
    """report_power's JSON as measure.tcl redirects it: OpenSTA's warnings
    (STA-2402, activity that did not converge) land in front of it."""
    lines = text.splitlines(True)
    while lines and lines[0].startswith("[WARNING "):
        lines.pop(0)
    return json.loads("".join(lines))


def split_arm(arm):
    m = re.match(r"(.+)_([a-z_]+?)_(\d+)$", arm)
    if not m:
        raise ValueError("arm %s is not <design>_<shape>_<period>" % arm)
    return m.group(1), m.group(2), int(m.group(3))


def collect(paths, arms):
    measured = {}
    times = collections.defaultdict(lambda: collections.defaultdict(float))
    for path in paths:
        base = os.path.basename(path)
        if base.endswith("_power.json"):
            arm = base[: -len("_power.json")]
            with open(path) as f:
                measured.setdefault(arm, {})["power_w"] = total_power(
                    load_power(f.read())
                )
        elif base.endswith(".json") and base[:-5] in arms:
            with open(path) as f:
                measured.setdefault(base[:-5], {}).update(json.load(f))
        elif base.endswith(".log"):
            arm = next((a for a in arms if "/%s/" % a in path), None)
            if arm is None:
                continue
            stage = next((s for s, p in STAGES if base.startswith(p)), None)
            if stage:
                with open(path, errors="replace") as f:
                    times[arm][stage] += seconds(f.read())
    return measured, times


def pct(new, old):
    return 100.0 * (new - old) / old


def rows(arms, measured):
    by_design = collections.defaultdict(dict)
    for arm in arms:
        design, shape, period = split_arm(arm)
        by_design[design].setdefault(shape, []).append((period, arm))
    out = []
    for design in sorted(by_design):
        shapes = by_design[design]
        # each shape's last-listed period is its calibrated run
        best = {s: measured.get(p[-1][1]) for s, p in shapes.items()}
        flops = best.get("flops")
        for shape in sorted(shapes, key=lambda s: (s != "flops", s)):
            m = best[shape]
            row = {"design": design, "shape": shape}
            if not m or "min_period_ps" not in m:
                row["note"] = "not yet measured"
            else:
                row.update(m)
                if flops and shape != "flops" and "min_period_ps" in flops:
                    for key in (
                        "min_period_ps",
                        "reg2reg_min_period_ps",
                        "stdcell_um2",
                        "power_w",
                    ):
                        if key in m and key in flops:
                            row["d_" + key] = pct(m[key], flops[key])
                    row["dominates"] = all(
                        row.get("d_" + k, 1) <= 0
                        for k in ("min_period_ps", "stdcell_um2", "power_w")
                    )
            out.append(row)
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--md", required=True)
    p.add_argument("--arms", required=True, help="comma-separated arm names")
    p.add_argument("files", nargs="*")
    a = p.parse_args(argv)
    arms = [x for x in a.arms.split(",") if x]
    measured, times = collect(a.files, arms)
    table = rows(arms, measured)
    cols = [
        "design",
        "shape",
        "period_ps",
        "min_period_ps",
        "d_min_period_ps",
        "reg2reg_min_period_ps",
        "d_reg2reg_min_period_ps",
        "stdcell_um2",
        "d_stdcell_um2",
        "power_w",
        "d_power_w",
        "cells",
        "dominates",
        "note",
    ]
    with open(a.csv, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in table:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    with open(a.md, "w") as f:
        f.write(
            "| design | shape | min period (ps) | Δ period | reg→reg (ps) | Δ reg→reg "
            "| std-cell µm² | Δ area | power (mW) | Δ power |\n"
        )
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in table:
            if r.get("note"):
                f.write(
                    "| %s | %s | %s | | | | | | | |\n"
                    % (r["design"], r["shape"], r["note"])
                )
                continue
            d = lambda k: ("%+.1f %%" % r[k]) if k in r else ""
            f.write(
                "| %s | %s | %.0f | %s | %s | %s | %.0f | %s | %.2f | %s |\n"
                % (
                    r["design"],
                    r["shape"],
                    r["min_period_ps"],
                    d("d_min_period_ps"),
                    (
                        ("%.0f" % r["reg2reg_min_period_ps"])
                        if "reg2reg_min_period_ps" in r
                        else ""
                    ),
                    d("d_reg2reg_min_period_ps"),
                    r["stdcell_um2"],
                    d("d_stdcell_um2"),
                    1000 * r.get("power_w", 0),
                    d("d_power_w"),
                )
            )
        f.write("\n| arm | " + " | ".join(s for s, _ in STAGES) + " | total |\n")
        f.write("|---|" + "---|" * (len(STAGES) + 1) + "\n")
        for arm in arms:
            t = times.get(arm, {})
            f.write(
                "| %s | %s | %.0f |\n"
                % (
                    arm,
                    " | ".join("%.0f" % t.get(s, 0) for s, _ in STAGES),
                    sum(t.values()),
                )
            )


if __name__ == "__main__":
    main()
