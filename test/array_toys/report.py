"""The toy scan as a table: per kind, depth and width, each arm's
synthesis time, period and area, from whatever the scan has built.

    report.py <bazel-bin/test/array_toys>
"""

import json
import os
import re
import sys

_ELAPSED = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):([\d.]+)")
_FLOW = re.compile(r"^(?P<kind>\w+?)_(?P<depth>\d+)x(?P<width>\d+)_(?P<arm>yosys|generate_ram)$")


def seconds(log):
    """A log's elapsed time, from the line ORFS's time wrapper writes."""
    with open(log) as f:
        for line in f:
            m = _ELAPSED.search(line)
            if m:
                h, mi, s = m.groups()
                return int(h or 0) * 3600 + int(mi) * 60 + float(s)
    return None


def synth_seconds(logs):
    """Synthesis: every 1_* step that ran, canonicalize to netlist."""
    total = 0.0
    for name in sorted(os.listdir(logs)):
        if name.startswith("1_") and name.endswith(".log") and "metrics" not in name:
            s = seconds(os.path.join(logs, name))
            if s is not None and name != "1_synth.log":
                total += s
    return total


def harvest(bin_dir):
    rows = {}
    for name in os.listdir(bin_dir):
        if not name.endswith("_period.json"):
            continue
        flow = name[: -len("_period.json")]
        m = _FLOW.match(flow)
        if not m:
            continue
        with open(os.path.join(bin_dir, name)) as f:
            probe = json.load(f)
        logs = os.path.join(bin_dir, "logs", "asap7", flow, "base")
        key = (m["kind"], int(m["depth"]), int(m["width"]))
        rows.setdefault(key, {})[m["arm"]] = probe | {"synth_s": synth_seconds(logs)}
    return rows


def main():
    rows = harvest(sys.argv[1])
    if not rows:
        sys.exit("no toy has been built: run the scan first")
    print("| kind | depth x width | yosys synth s | yosys ps | yosys um2 | gen synth s | gen ps | gen um2 |")
    print("|---|---|--:|--:|--:|--:|--:|--:|")
    for (kind, depth, width), arms in sorted(rows.items()):
        y = arms.get("yosys", {})
        g = arms.get("generate_ram", {})

        def cell(arm, key, fmt):
            return fmt % arm[key] if key in arm else ""

        print(
            f"| {kind} | {depth} x {width} | {cell(y, 'synth_s', '%.1f')} | {cell(y, 'period_ps', '%.0f')} "
            f"| {cell(y, 'area_um2', '%.0f')} | {cell(g, 'synth_s', '%.1f')} | {cell(g, 'period_ps', '%.0f')} "
            f"| {cell(g, 'area_um2', '%.0f')} |"
        )


if __name__ == "__main__":
    main()
