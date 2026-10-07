"""One ladder row: flip-flops against the register file, at global route.

Reads each arm's stage logs (wall time) and 5_1_grt.json (the metrics
ORFS reports at the end of global route, with global-route parasitics)
and writes one JSON row. A missing log, elapsed line or metric is an
error: a row that silently lacks a number would read as a result.
"""

import argparse
import json
import os
import re
import sys

ELAPSED_RE = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\[h:\]min:sec")

# ORFS metric -> row field. fmax is 1 / (period - worst slack), the
# minimum period the stage would meet, as the period the pass rule reads.
METRICS = {
    "fmax": "globalroute__timing__fmax",
    "setup_ws": "globalroute__timing__setup__ws",
    "hold_ws": "globalroute__timing__hold__ws",
    "stdcell_area": "globalroute__design__instance__area__stdcell",
    "core_area": "globalroute__design__core__area",
    "power": "globalroute__power__total",
    "instances": "globalroute__design__instance__count__stdcell",
}


def stage_seconds(path):
    with open(path) as f:
        m = ELAPSED_RE.search(f.read())
    if not m:
        sys.exit("no elapsed time in %s" % path)
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + float(s)


def metric(metrics, key, path):
    if key in metrics:
        return metrics[key]
    # Per-clock metrics carry a suffix, e.g. fmax__clock:clk.
    hits = [k for k in metrics if k.startswith(key + "__")]
    if len(hits) == 1:
        return metrics[hits[0]]
    sys.exit(
        "%s: metric %s not found once (%s); have: %s"
        % (
            path,
            key,
            hits,
            ", ".join(sorted(k for k in metrics if k.startswith("globalroute"))),
        )
    )


def arm(files):
    logs = {}
    grt = None
    for f in files:
        base = os.path.basename(f)
        if base == "5_1_grt.json":
            grt = f
        elif re.match(r"[1-5]_.*\.log$", base) and not base.endswith("_metrics.log"):
            logs[base[: -len(".log")]] = stage_seconds(f)
    if grt is None:
        sys.exit("no 5_1_grt.json among %s" % files)
    with open(grt) as f:
        metrics = json.load(f)
    row = {k: metric(metrics, v, grt) for k, v in METRICS.items()}
    # fmax is in Hz; a period outside 10 ps .. 1 us means the unit moved.
    row["min_period_ps"] = 1e12 / row["fmax"]
    if not 10 <= row["min_period_ps"] <= 1e6:
        sys.exit("%s: fmax %r is not in Hz" % (grt, row["fmax"]))
    row["stage_seconds"] = logs
    row["total_seconds"] = sum(logs.values())
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--flops", nargs="+", required=True)
    p.add_argument("--regfile", nargs="+", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    flops = arm(a.flops)
    regfile = arm(a.regfile)
    delta = 100.0 * (regfile["min_period_ps"] / flops["min_period_ps"] - 1)
    row = {
        "name": a.name,
        "flops": flops,
        "regfile": regfile,
        "period_delta_percent": delta,
        "passes": delta <= 3.0,
    }
    with open(a.out, "w") as f:
        json.dump(row, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
