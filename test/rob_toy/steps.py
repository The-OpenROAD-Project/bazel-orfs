"""Seconds per flow step of the toy Rob sizes that have been built.

steps.py <bazel-bin/test/rob_toy>
"""

import os
import re
import sys

_ELAPSED = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):([\d.]+)")
_FLOW = re.compile(r"^rob_\d+(_rtl|_abc|_plain)?(_repair)?(_\w+)?$")


def seconds(log):
    """A log's elapsed time, from the line ORFS's time wrapper writes."""
    with open(log) as f:
        for line in f:
            m = _ELAPSED.search(line)
            if m:
                h, mi, s = m.groups()
                return int(h or 0) * 3600 + int(mi) * 60 + float(s)
    return None


def main():
    root = os.path.join(sys.argv[1], "logs", "asap7")
    for flow in sorted(os.listdir(root), key=lambda f: (len(f), f)):
        if not _FLOW.match(flow):
            continue
        logs = os.path.join(root, flow, "base")
        steps = []
        for name in sorted(os.listdir(logs)):
            if name.endswith(".log") and "metrics" not in name:
                t = seconds(os.path.join(logs, name))
                if t is not None:
                    steps.append((name[: -len(".log")], t))
        total = sum(t for _, t in steps)
        print(f"{flow}: {total:.0f} s")
        for name, t in steps:
            print(f"  {name:28} {t:7.1f}")


if __name__ == "__main__":
    main()
