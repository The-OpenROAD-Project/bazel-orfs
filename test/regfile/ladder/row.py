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

# ORFS metric -> row field. fmax is 1 / sta::find_clk_min_period with
# port paths ignored: the register-to-register minimum period, the one
# the pass rule reads (only register-to-register paths can fail timing
# closure; boundary paths are the parent's). setup_ws is over all paths.
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
    """The stage's wall time, or None for a synthesis log bazel-orfs
    writes without one; an OpenROAD stage log without one is an error."""
    with open(path) as f:
        m = ELAPSED_RE.search(f.read())
    if not m:
        if os.path.basename(path).startswith("1_"):
            return None
        sys.exit("no elapsed time in %s" % path)
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + float(s)


STAMP_RE = re.compile(r"^\[\s*(\d+(?:\.\d+)?)\]\s?")


def repair_progress(path):
    """repair_timing's progress rows in a stage log: per row the
    iteration ("final" for the last), the moves so far, WNS, TNS and
    violating endpoints, and the seconds into the stage when the log line
    carries ORFS's elapsed stamp. Where the WNS column stops moving is
    where repair stopped making progress on the period."""
    rows = []
    with open(path, errors="replace") as f:
        for line in f:
            t = None
            m = STAMP_RE.match(line)
            if m:
                t = float(m.group(1))
                line = line[m.end() :]
            f_ = [x.strip() for x in line.split("|")]
            if len(f_) < 11 or not (f_[0].isdigit() or f_[0] == "final"):
                continue
            try:
                moves = sum(int(x) for x in f_[1:6])
                rows.append(
                    {
                        "seconds": t,
                        "iter": f_[0],
                        "moves": moves,
                        "wns": float(f_[7]),
                        "tns": float(f_[-3]),
                        "violators": int(f_[-2]),
                    }
                )
            except ValueError:
                continue
    return rows


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
    unmeasured = []
    grt = None
    grt_log = None
    for f in files:
        base = os.path.basename(f)
        if base == "5_1_grt.json":
            grt = f
        elif base == "5_1_grt.log":
            grt_log = f
        elif re.match(r"[1-5]_.*\.log$", base) and not base.endswith("_metrics.log"):
            t = stage_seconds(f)
            if t is None:
                unmeasured.append(base)
            else:
                logs[base[: -len(".log")]] = t
    if grt is None:
        sys.exit("no 5_1_grt.json among %s" % files)
    with open(grt) as f:
        metrics = json.load(f)
    row = {k: metric(metrics, v, grt) for k, v in METRICS.items()}
    # Macros: AUTO_MEMORIES, which a register file needs, may turn other
    # memories into macros too; a row whose arms differ here is not like
    # for like.
    row["macros"] = metric(metrics, "globalroute__design__instance__count__macros", grt)
    # fmax is in Hz; a period outside 10 ps .. 1 us means the unit moved.
    row["min_period_ps"] = 1e12 / row["fmax"]
    if not 10 <= row["min_period_ps"] <= 1e6:
        sys.exit("%s: fmax %r is not in Hz" % (grt, row["fmax"]))
    row["stage_seconds"] = logs
    row["total_seconds"] = sum(logs.values())
    # repair_timing at global route: where it made progress and where it
    # ground on.
    row["grt_repair"] = repair_progress(grt_log) if grt_log else None
    # Synthesis logs without an elapsed line: not in total_seconds.
    row["unmeasured_logs"] = sorted(unmeasured)
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
        "like_for_like": flops["macros"] == regfile["macros"],
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
