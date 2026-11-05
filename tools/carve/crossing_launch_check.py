"""The launch-side bound's check, on a design small enough to time in
seconds: for every crossing set, the worst crossing a launcher launches is
the set's worst crossing in crossing_time's report, each room is the
smaller of its setup and hold slack and never below zero, each bound is
its crossing less its room, and the hold counts nest.

    crossing_launch_check.py <launch dir> <crossing_time dir>

Each dir holds cross.txt.<n>, one per set: crossing_launch.tcl's JSON, and
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


def check_launcher(n, e):
    errors = []
    name = "set %d %s" % (n, e["flop"])
    # an unconstrained pin's INF slack is written as null: no limit
    if e["hold_fanout"] is not None:
        setup = float("inf") if e["setup_d"] is None else e["setup_d"]
        room = max(0.0, min(setup, e["hold_fanout"]))
        if abs(e["room"] - room) > EPS:
            errors.append("%s: room %s, not min(setup, hold)" % (name, e["room"]))
        if abs(e["bound"] - (e["crossing_ps"] - e["room"])) > EPS:
            errors.append("%s: bound %s is not crossing less room" % (name, e["bound"]))
    if "fanout" in e:
        counts = [e["hold_under_100"], e["hold_under_300"], e["hold_under_to"]]
        if counts != sorted(counts) or counts[-1] > e["fanout"]:
            errors.append(
                "%s: hold counts do not nest: %s of %d" % (name, counts, e["fanout"])
            )
        if e["pad_ps"] < 0 or (counts[-1] == 0) != (e["pad_ps"] == 0):
            errors.append(
                "%s: padding %s for %d endpoints" % (name, e["pad_ps"], counts[-1])
            )
    return errors


def check(launch_dir, time_dir):
    errors = []
    sets = sorted(
        int(m.group(1))
        for m in (re.fullmatch(r"cross\.txt\.(\d+)", f) for f in os.listdir(launch_dir))
        if m
    )
    if not sets:
        errors.append("no launch reports in %s" % launch_dir)
    for n in sets:
        with open(os.path.join(launch_dir, "cross.txt.%d" % n)) as f:
            report = json.load(f)
        want = worst_crossing(os.path.join(time_dir, "cross.txt.%d" % n))
        launchers = report["launchers"]
        if want is None:
            if launchers:
                errors.append("set %d: crossing_time has no crossing, launch does" % n)
            continue
        got = max((e["crossing_ps"] for e in launchers), default=None)
        # crossing_paths.tcl writes one decimal
        if got is None or abs(got - want) > 0.05 + EPS:
            errors.append(
                "set %d: worst launched crossing %s, crossing_time %.1f"
                % (n, got, want)
            )
        for e in launchers:
            errors += check_launcher(n, e)
    return errors


if __name__ == "__main__":
    errs = check(sys.argv[1], sys.argv[2])
    for e in errs:
        print(e)
    sys.exit(1 if errs else 0)
