#!/usr/bin/env python3
"""Read what a repair_timing call wrote about itself into an ORFS log.

Nothing here is instrumentation. With `-verbose` rsz prints one progress
row per optimisation iteration, and ORFS's helper always passes
`-verbose`, so every design in the flow already records the whole
trajectory of every repair_timing call:

    repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose
    [INFO RSZ-0099] Repairing 17228 out of 17228 (100.00%) violating endpoints...
       Iter   | Removed | Resized | Inserted | Cloned |  Pin  |   Area   |    WNS   |   StTNS    |   EnTNS    |  Viol  |  Worst
              | Buffers |  Gates  | Buffers  |  Gates | Swaps |          |          |            |            | Endpts | St/EnPt
    ------------------------------------------------------------------------------------------------------------------------------
           0* |       0 |       0 |        0 |      0 |     0 |    +0.0% | -2082.577 | -6150547.0 | -10232514.0 |  17228 | core/...
          10* |       0 |       1 |        5 |      0 |     4 |    +0.0% | -2029.806 | -6013988.5 | -10185645.0 |  17228 | core/...
        final |       3 |     211 |       57 |     38 |   176 |    +0.1% | -2015.784 | -5993589.0 | -10172325.0 |  17228 | core/...
    [WARNING RSZ-0062] Unable to repair all setup violations.
    [INFO RSZ-0505] Runtime: 634.78s
    [INFO RSZ-0033] No hold violations found.
    [INFO RSZ-0506] Runtime: 0.87s
    Took 636 seconds: repair_timing -setup_margin 0 -hold_margin 0 -repair_tns 100 -verbose

The marker after the iteration number is the phase: `*` is the main
(LEGACY) repair, `+` is last gasp. The echoed command line is the knob
witness: ORFS's helper appends `-repair_tns $TNS_END_PERCENT` and the
`-skip_*` flags from the environment, so what the tool was actually
asked for is on the line, and an arm whose echo disagrees with its knob
is discarded rather than averaged in.

With `RUN_CMD` pointed at log_timestamps.py every row also carries
elapsed seconds since the substep started, which turns the trajectory
into a time series: how many seconds of the grind bought the last
picosecond of WNS.

Units: WNS and TNS are whatever the log prints, which for asap7 is
picoseconds (`set_cmd_units -time ps`). This reader does not convert.
"""

import re

_STAMP = r"^(?:\[\s*(\d+(?:\.\d+)?)\]\s?)?"

# The echoed command. util.tcl's log_cmd prints the command before
# running it; `Took N seconds: <cmd>` after.
_CMD = re.compile(_STAMP + r"(repair_timing|repair_design)(\s.*)?$")
_TOOK = re.compile(_STAMP + r"Took (\d+) seconds: (repair_timing|repair_design)(.*)$")

_REPAIRING = re.compile(
    _STAMP
    + r"\[INFO RSZ-0099\] Repairing (\d+) out of (\d+) \(([\d.]+)%\) violating endpoints"
)

# One progress row. Iteration is a number or `final`; the marker is one
# character or absent (the `final` row has none).
_ROW = re.compile(
    _STAMP
    + r"\s*(\d+|final)([*+]?)\s*\|\s*(-?\d+)\s*\|\s*(-?\d+)\s*\|\s*(-?\d+)\s*\|"
    + r"\s*(-?\d+)\s*\|\s*(-?\d+)\s*\|\s*([+-][\d.]+)%\s*\|"
    + r"\s*(-?[\d.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*(\d+)\s*\|"
)

_RUNTIME = re.compile(_STAMP + r"\[INFO RSZ-(050[4-7])\] Runtime: ([\d.]+)s")
_UNREPAIRED = re.compile(_STAMP + r"\[WARNING RSZ-0062\] Unable to repair all setup")
_NO_HOLD = re.compile(_STAMP + r"\[INFO RSZ-0033\] No hold violations found")
_HOLD_BUFFERS = re.compile(_STAMP + r"\[INFO RSZ-0032\] Inserted (\d+) hold buffers")

# The study's instrumentation (patches/0066): one key=value line per
# phase, seconds and counts, printed by the profiled binary only.
_PROFILE = re.compile(_STAMP + r"\[RSZ-PROFILE\] (.*)$")

# Which RSZ runtime line belongs to which command.
RUNTIME_OWNER = {
    "0504": "repair_design",
    "0505": "setup",
    "0506": "hold",
    "0507": "recover_power",
}


def _stamp(match):
    value = match.group(1)
    return float(value) if value is not None else None


def parse_args(text):
    """The knobs on an echoed repair_timing line, as a dict.

    `-setup_margin 0 -repair_tns 100 -skip_last_gasp -verbose` becomes
    {"setup_margin": "0", "repair_tns": "100", "skip_last_gasp": True,
    "verbose": True}. `-sequence "vt_swap reroute"` keeps its quoted value.
    """
    out = {}
    # A value is a quoted string, a number (which may be negative, so a
    # leading minus followed by a digit is not a flag), or a bare word.
    tokens = re.findall(
        r'-([A-Za-z_]\w*)(?:\s+("[^"]*"|-?\d[^\s]*|[^\s-][^\s]*))?', text or ""
    )
    for key, value in tokens:
        out[key] = value.strip('"') if value else True
    return out


def parse_log(text):
    """Every repair_timing / repair_design call in one substep log.

    Returns a list of dicts, one per echoed command, in log order:

        command      "repair_timing" | "repair_design"
        args         parse_args() of the echo
        start_s      elapsed stamp of the echo (None when unstamped)
        took_s       ORFS's `Took` for the command (None if absent)
        setup_s, hold_s, repair_design_s   RSZ Runtime lines inside it
        repairing    (n, of, percent) from RSZ-0099
        rows         progress rows: dicts with iter (int or "final"),
                     marker, removed, resized, inserted, cloned, swaps,
                     area_pct, wns, st_tns, en_tns, viol_endpoints, t_s
        unrepaired   RSZ-0062 seen
        hold_buffers int or 0; None if hold did not run
    """
    calls = []
    current = None
    for line in text.splitlines():
        m = _CMD.match(line)
        if m and not line.lstrip("[]0123456789. ").startswith("Took"):
            current = {
                "command": m.group(2),
                "args": parse_args(m.group(3)),
                "start_s": _stamp(m),
                "took_s": None,
                "setup_s": None,
                "hold_s": None,
                "repair_design_s": None,
                "repairing": None,
                "rows": [],
                "unrepaired": False,
                "hold_buffers": None,
                "profile": {},
            }
            calls.append(current)
            continue
        if current is None:
            continue
        m = _TOOK.match(line)
        if m:
            current["took_s"] = int(m.group(2))
            current = None
            continue
        m = _REPAIRING.match(line)
        if m:
            current["repairing"] = (int(m.group(2)), int(m.group(3)), float(m.group(4)))
            continue
        m = _ROW.match(line)
        if m:
            it = m.group(2)
            current["rows"].append(
                {
                    "iter": int(it) if it != "final" else "final",
                    "marker": m.group(3),
                    "removed": int(m.group(4)),
                    "resized": int(m.group(5)),
                    "inserted": int(m.group(6)),
                    "cloned": int(m.group(7)),
                    "swaps": int(m.group(8)),
                    "area_pct": float(m.group(9)),
                    "wns": float(m.group(10)),
                    "st_tns": float(m.group(11)),
                    "en_tns": float(m.group(12)),
                    "viol_endpoints": int(m.group(13)),
                    "t_s": _stamp(m),
                }
            )
            continue
        m = _RUNTIME.match(line)
        if m:
            owner = RUNTIME_OWNER[m.group(2)]
            key = {"setup": "setup_s", "hold": "hold_s",
                   "repair_design": "repair_design_s"}.get(owner)
            if key:
                current[key] = float(m.group(3))
            continue
        if _UNREPAIRED.match(line):
            current["unrepaired"] = True
            continue
        if _NO_HOLD.match(line):
            current["hold_buffers"] = 0
            continue
        m = _HOLD_BUFFERS.match(line)
        if m:
            current["hold_buffers"] = int(m.group(2))
            continue
        m = _PROFILE.match(line)
        if m:
            fields = dict(kv.split("=", 1) for kv in m.group(2).split())
            phase = fields.pop("phase", "?")
            current["profile"][phase] = {
                k: (float(v) if "." in v else int(v)) for k, v in fields.items()
            }
    return calls


def useful_prefix(rows, eps_wns_ps=0.5, eps_tns_rel=1e-4):
    """How much of the trajectory bought anything.

    The last main-phase iteration whose row improved WNS by more than
    `eps_wns_ps`, or TNS by more than `eps_tns_rel` of the starting TNS,
    over the best seen so far; the elapsed stamp there; and the run's
    end. The ratio is the share of the grind that produced nothing --
    the number this study exists to measure. TNS gets a relative
    threshold because on a design with ten thousand violating endpoints
    it wobbles by hundreds of picoseconds per row without going
    anywhere. Stamps are None on an unstamped log; iterations are always
    available.
    """
    numbered = [r for r in rows if r["iter"] != "final" and r["marker"] == "*"]
    if not numbered:
        return None
    best_wns = numbered[0]["wns"]
    best_tns = numbered[0]["en_tns"]
    eps_tns = abs(best_tns) * eps_tns_rel
    last = numbered[0]
    for row in numbered[1:]:
        if row["wns"] > best_wns + eps_wns_ps or row["en_tns"] > best_tns + eps_tns:
            best_wns = max(best_wns, row["wns"])
            best_tns = max(best_tns, row["en_tns"])
            last = row
    end = numbered[-1]
    for row in rows:
        if row["iter"] == "final":
            end = row
    return {
        "last_improving_iter": last["iter"],
        "t_last_improvement_s": last["t_s"],
        "final_iter": numbered[-1]["iter"],
        "t_final_s": end["t_s"],
        "wns_start": numbered[0]["wns"],
        "wns_end": end["wns"],
        "tns_start": numbered[0]["en_tns"],
        "tns_end": end["en_tns"],
    }


def summarize(calls):
    """One row per call, the shape the census table wants."""
    out = []
    for call in calls:
        row = {
            "command": call["command"],
            "kind": _kind(call),
            "took_s": call["took_s"],
            "start_s": call["start_s"],
            "setup_s": call["setup_s"],
            "hold_s": call["hold_s"],
            "repair_design_s": call["repair_design_s"],
            "iterations": max(
                [r["iter"] for r in call["rows"] if r["iter"] != "final"],
                default=0,
            ),
            "endpoints": call["repairing"][1] if call["repairing"] else None,
            "unrepaired": call["unrepaired"],
            "hold_buffers": call["hold_buffers"],
            "profile": call["profile"],
            "witness": call["args"],
        }
        prefix = useful_prefix(call["rows"])
        if prefix:
            row.update(prefix)
        out.append(row)
    return out


def _kind(call):
    """Which of ORFS's call sites this is, from the echoed arguments."""
    if call["command"] == "repair_design":
        return "repair_design"
    args = call["args"]
    seq = args.get("sequence")
    if isinstance(seq, str) and "reroute" in seq:
        return "post_grt_wns"
    if args.get("setup") is True and args.get("skip_last_gasp") is True:
        return "floorplan_setup"
    return "setup_hold"
