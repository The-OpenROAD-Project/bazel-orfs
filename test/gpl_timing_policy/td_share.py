#!/usr/bin/env python3
"""Summarise what timing-driven re-weights cost in a timestamped 3_3_place_gp.log.

Usage: td_share.py [--detail] NAME=LOG [NAME=LOG ...]

Each re-weight is timed from its GPL-0101 line (just before rsz is called)
to its GPL-0106 line (slacks back, weights about to be set). Prints one
summary line per log plus the per-iteration times; never the log itself.
"""

import re
import sys

STAMP = re.compile(r"^\[\s*([0-9.]+)\]\s?(.*)$")


def summarise(name, path):
    first = last = None
    iters = []
    cur = None
    buffers = []
    with open(path, errors="replace") as f:
        for line in f:
            m = STAMP.match(line)
            if not m:
                continue
            t, body = float(m.group(1)), m.group(2)
            if "GPL-" in body:
                if first is None and "GPL-0002" in body:
                    first = t
                last = t
            if "GPL-0100" in body:
                v = re.search(r"virtual: (\w+)", body)
                cur = {"virtual": v.group(1) if v else "?"}
            elif "GPL-0101" in body and cur is not None:
                o = re.search(r"overflow: ([0-9.]+)", body)
                cur["overflow"] = float(o.group(1)) if o else None
                cur["t0"] = t
            elif "GPL-0106" in body and cur is not None and "t0" in cur:
                cur["dt"] = t - cur["t0"]
                iters.append(cur)
                cur = None
            elif re.search(r"Inserted (\d+) buffers", body):
                buffers.append(int(re.search(r"Inserted (\d+) buffers", body).group(1)))
    if first is None:
        print(f"{name}: no GPL-0002 line, not a gpl log or no timestamps")
        return
    total = last - first
    td = sum(i["dt"] for i in iters)
    share = 100.0 * td / total if total else 0.0
    print(
        f"{name}: gpl {total:.1f} s, {len(iters)} re-weights {td:.1f} s ({share:.0f} %), "
        f"buffers inserted per repair {buffers if buffers else '-'}"
    )
    for i in iters:
        print(
            f"    overflow {i.get('overflow')}, virtual {i['virtual']}: {i['dt']:.1f} s"
        )


def detail(name, path, limit=40):
    """The tool messages inside each re-weight, with the gap since the last one."""
    on = False
    prev = None
    shown = 0
    print(f"{name}:")
    with open(path, errors="replace") as f:
        for line in f:
            m = STAMP.match(line)
            if not m:
                continue
            t, body = float(m.group(1)), m.group(2)
            if "GPL-0101" in body:
                on, prev, shown = True, t, 0
                print("    -- re-weight")
                continue
            if not on:
                continue
            if re.search(r"\[(INFO|WARNING) [A-Z]+-\d+\]", body) or "GPL-0106" in body:
                if shown < limit:
                    print(f"    +{t - prev:7.2f} s  {body[:110]}")
                    shown += 1
                prev = t
            if "GPL-0106" in body:
                on = False


def main():
    args = sys.argv[1:]
    show = args and args[0] == "--detail"
    for arg in args[1:] if show else args:
        name, path = arg.split("=", 1)
        (detail if show else summarise)(name, path)


if __name__ == "__main__":
    main()
