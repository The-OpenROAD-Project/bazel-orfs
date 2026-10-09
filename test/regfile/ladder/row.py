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

# ORFS metric -> row field. setup_ws is over all paths. The period the
# pass rule reads is not ORFS's aggregate timing__fmax: that is the
# maximum over the clocks, the most optimistic one when a design has a
# second (virtual) clock. It is the slowest clock's own
# timing__fmax__clock:<name>, 1 / sta::find_clk_min_period with port
# paths included: the clock period minus that clock's worst setup slack.
METRICS = {
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
            # The iteration carries repair_timing's phase marker: `10*` in
            # the main phases, `1500+` in last gasp; the counter restarts per
            # phase, so log order, not the number, is the time axis.
            it = re.fullmatch(r"(\d+)([*+]?)|final", f_[0]) if len(f_) >= 11 else None
            if not it:
                continue
            try:
                moves = sum(int(x) for x in f_[1:6])
                rows.append(
                    {
                        "seconds": t,
                        "iter": f_[0],
                        "phase": (
                            "final"
                            if f_[0] == "final"
                            else ("last_gasp" if it.group(2) == "+" else "main")
                        ),
                        "moves": moves,
                        "wns": float(f_[7]),
                        "tns": float(f_[-3]),
                        "violators": int(f_[-2]),
                    }
                )
            except ValueError:
                continue
    return rows


TOOK_RE = re.compile(r"^Took (\d+) seconds: (.*)$")


def commands(path):
    """The commands ORFS's log_cmd timed in a stage log (it reports those
    of 5 s or more): where a stage's time goes, command by command."""
    out = []
    with open(path, errors="replace") as f:
        for line in f:
            m = TOOK_RE.match(line.strip())
            if m:
                out.append({"seconds": int(m.group(1)), "cmd": m.group(2)[:120]})
    return out


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
    timed = {}
    repairs = {}
    for f in files:
        base = os.path.basename(f)
        if base == "5_1_grt.json":
            grt = f
        elif re.match(r"[1-5]_.*\.log$", base) and not base.endswith("_metrics.log"):
            if base == "5_1_grt.log":
                grt_log = f
            cmds = commands(f)
            if cmds:
                timed[base[: -len(".log")]] = cmds
            if base in ("4_1_cts.log", "5_1_grt.log"):
                repairs[base[: -len(".log")]] = repair_progress(f)
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
    per_clock = {
        k.split("clock:", 1)[1]: v
        for k, v in metrics.items()
        if k.startswith("globalroute__timing__fmax__clock:")
    }
    if not per_clock:
        sys.exit("%s: no globalroute__timing__fmax__clock:<name> metric" % grt)
    row["fmax_per_clock"] = per_clock
    row["fmax"] = min(per_clock.values())
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
    # Where each stage's time goes, by command, and repair_timing's
    # progress in each stage that repairs.
    row["commands"] = timed
    row["repair"] = repairs
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
