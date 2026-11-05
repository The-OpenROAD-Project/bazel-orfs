"""The headroom's check, on a design small enough to time in seconds: for
every crossing set, the period the headroom measures is the worst crossing
crossing_time.tcl reports for that set, each what-if is undone, and no
move reads worse than the design as built.

    crossing_headroom_check.py <headroom dir> <crossing_time dir>

Each dir holds cross.txt.<n>, one per set: the headroom's JSON, and
crossing_paths.tcl's report (need_ps kind from to start end ...).
"""

import json
import os
import re
import sys

EPS = 0.05


def worst_crossing(path):
    worst = None
    with open(path) as f:
        for line in f:
            fields = line.split()
            if len(fields) > 1 and fields[1] == "crossing":
                need = float(fields[0])
                worst = need if worst is None else max(worst, need)
    return worst


def check(headroom_dir, time_dir):
    errors = []
    sets = sorted(
        int(m.group(1))
        for m in (
            re.fullmatch(r"cross\.txt\.(\d+)", n) for n in os.listdir(headroom_dir)
        )
        if m
    )
    if not sets:
        errors.append("no headroom reports in %s" % headroom_dir)
    for n in sets:
        with open(os.path.join(headroom_dir, "cross.txt.%d" % n)) as f:
            hr = json.load(f)
        want = worst_crossing(os.path.join(time_dir, "cross.txt.%d" % n))
        if want is None:
            if "period" in hr:
                errors.append(
                    "set %d: crossing_time has no crossing, headroom does" % n
                )
            continue
        period = hr["period"]["period"]
        # crossing_paths.tcl writes one decimal
        if abs(period - want) > 0.05 + EPS:
            errors.append(
                "set %d: headroom period %.2f, crossing_time %.1f" % (n, period, want)
            )
        for m, key in (("wire", "floor"), ("vt", "vt"), ("skew", "skew")):
            if m not in hr:
                continue
            if abs(hr[m]["restored"] - period) > EPS:
                errors.append("set %d: %s not undone: %s" % (n, m, hr[m]["restored"]))
            if hr[m][key] > period + EPS:
                errors.append("set %d: %s reads worse than as built" % (n, m))
    return errors


if __name__ == "__main__":
    errs = check(sys.argv[1], sys.argv[2])
    for e in errs:
        print(e)
    sys.exit(1 if errs else 0)
