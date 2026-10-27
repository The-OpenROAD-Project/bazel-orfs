"""Turnaround of the toy flows: seconds per stage, per kind, size and arm,
from whatever stages the scan has built.

    turnaround.py <bazel-bin/test/array_toys>
"""

import os
import re
import sys

from report import seconds

_FLOW = re.compile(
    r"^(?P<kind>\w+?)_(?P<depth>\d+)x(?P<width>\d+)_(?P<arm>yosys|generate_ram|structgen)$"
)
_STAGES = [
    ("synth", "1_"),
    ("floorplan", "2_"),
    ("place", "3_"),
    ("cts", "4_"),
    ("grt", "5_"),
]


def stage_seconds(logs):
    """Each stage's seconds: its steps' logs summed; None when not run."""
    out = {}
    names = sorted(os.listdir(logs)) if os.path.isdir(logs) else []
    for stage, prefix in _STAGES:
        steps = [
            n
            for n in names
            if n.startswith(prefix)
            and n.endswith(".log")
            and "metrics" not in n
            and n != "1_synth.log"
        ]
        times = [seconds(os.path.join(logs, n)) for n in steps]
        times = [t for t in times if t is not None]
        out[stage] = sum(times) if times else None
    return out


def main():
    logs_root = os.path.join(sys.argv[1], "logs", "asap7")
    rows = []
    for flow in sorted(os.listdir(logs_root)):
        m = _FLOW.match(flow)
        if m:
            rows.append(
                (
                    m["kind"],
                    int(m["depth"]),
                    int(m["width"]),
                    m["arm"],
                    stage_seconds(os.path.join(logs_root, flow, "base")),
                )
            )
    if not rows:
        sys.exit("no toy has been built: run the scan first")
    print(
        "| kind | depth x width | arm | "
        + " | ".join(s for s, _ in _STAGES)
        + " | total |"
    )
    print("|---|---|---|" + "--:|" * (len(_STAGES) + 1))
    for kind, depth, width, arm, st in sorted(rows):
        cells = ["%.0f" % st[s] if st[s] is not None else "" for s, _ in _STAGES]
        total = sum(v for v in st.values() if v is not None)
        print(
            f"| {kind} | {depth} x {width} | {arm} | "
            + " | ".join(cells)
            + f" | {total:.0f} |"
        )


if __name__ == "__main__":
    main()
