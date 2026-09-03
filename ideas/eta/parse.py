#!/usr/bin/env python3
"""Extract iterative-stage progress series from OpenROAD/ORFS logs.

Three OpenROAD stages grind: global placement, `repair_design` and
`repair_timing`. Each prints a progress table on a fixed interval, and
each has a *known termination condition* -- a metric that has to reach a
target before the stage stops. That pairing is what makes a forecast
conceivable at all: a series plus the value it is heading for.

The formats parsed here are, verbatim from OpenROAD:

  gpl   nesterovBase.cpp:3540   "{:9d} | {:8.4f} | {:13.6e} | {:+7.2f}% | ..."
                                 iter | overflow | HPWL(um) | HPWL% | penalty
  rsz   RepairDesign.cc:2411    "{: >9s} | {: >+8.1f}% | {: >7d} | {: >7d} |
                                  {: >13d} | {: >9d}"
                                 iter | area | resized | buffers | repaired |
                                 remaining
  rsz   OptimizationPolicy.cc   iter | removed | resized | inserted | cloned |
                                 pin | area | WNS | StTNS | EnTNS | viol | worst
  rsz   RepairHold.cc:814       iter | resized | buffers | cloned | area |
                                 WNS | TNS | endpoint

They are matched loosely on shape (a pipe-separated row under a known
header) rather than on exact column widths, so a formatting tweak
upstream does not silently drop a series -- but the header itself is
matched strictly, so a *column* change does fail loudly. Getting that
wrong in the other direction would mean forecasting the wrong number.
"""

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# --- headers that open a progress table ------------------------------------
#
# Matched on the column names, collapsed on whitespace, so column widths
# may drift but a renamed or reordered column does not parse.

GPL_HEADER = "Iteration | Overflow | HPWL (um) | HPWL(%) | Penalty | Group"

RD_HEADER = "Iteration | Area | Resized | Buffers | Nets repaired | Remaining"

RT_SETUP_HEADER_1 = (
    "Iter | Removed | Resized | Inserted | Cloned | Pin | Area | WNS | "
    "StTNS | EnTNS | Viol | Worst"
)

RT_HOLD_HEADER = (
    "Iteration | Resized | Buffers | Cloned Gates | Area | WNS | TNS | Endpoint"
)


def _norm(line):
    """Collapse whitespace so header matching survives width changes."""
    return " ".join(line.split())


def _num(tok):
    """Parse an OpenROAD numeric cell: '+3.1%', '1.2e+03', '-0.043', 'INF'."""
    tok = tok.strip().rstrip("%")
    if not tok:
        return None
    if tok.upper() in ("INF", "+INF", "-INF"):
        return float("inf") if not tok.startswith("-") else float("-inf")
    try:
        return float(tok)
    except ValueError:
        return None


@dataclass
class Point:
    """One row of a progress table."""

    iteration: int
    metric: float
    fields: dict = field(default_factory=dict)
    # Wall-clock seconds since the series' first row. Only present when the
    # log was stamped live; None for a post-mortem read.
    t: float = None


@dataclass
class Series:
    """One grind, with the target its metric is heading for."""

    kind: str  # gpl | repair_design | repair_setup | repair_hold
    design: str
    stage: str
    log: str
    metric_name: str
    target: float
    points: list = field(default_factory=list)
    # Wall time of the whole command, from ORFS "Took N seconds:".
    took_s: float = None
    # The grind ended (a "final" row, or the metric crossed the target).
    terminated: bool = False
    # It ended *at the target*. The distinction matters more than it
    # looks: repair_timing frequently stops on a pass or TNS limit with
    # violating endpoints still outstanding -- ibex floorplan goes 1970
    # -> 1970, spending 70 seconds to achieve nothing. For those runs
    # "when does it cross" has no answer, and the forecast worth having
    # is whether more time buys anything at all.
    converged: bool = False

    def to_json(self):
        d = asdict(self)
        return json.dumps(d)


# The elapsed-seconds prefix written by --@bazel-orfs//:log_timestamps.
# Stripped before matching, and kept as the point's wall-clock time --
# it is the only per-line timing an ORFS log ever carries.
STAMP_RE = re.compile(r"^\[\s*(\d+\.\d+)\]\s(.*)$", re.DOTALL)


def unstamp(line):
    """Split a log line into (seconds_or_None, rest)."""
    m = STAMP_RE.match(line)
    if m:
        return float(m.group(1)), m.group(2)
    return None, line


# ORFS util.tcl:24 -- the only wall-clock in a post-mortem log.
TOOK_RE = re.compile(r"^Took (\d+) seconds: (\S+)")

# gpl -overflow target, echoed by the ORFS command line log_cmd prints.
OVERFLOW_ARG_RE = re.compile(r"-overflow\s+([0-9.]+)")

DEFAULT_GPL_OVERFLOW = 0.1


def _is_iteration(tok):
    return tok == "final" or tok.rstrip("*").isdigit()


def _iteration_of(tok):
    return 0 if tok == "final" else int(tok.rstrip("*"))


def _row_cells(line):
    if "|" not in line:
        return None
    cells = [c.strip() for c in line.split("|")]
    # A table row leads with an iteration number, or the literal "final".
    # repair_timing marks some iterations with a trailing "*", and
    # rejecting those drops the entire setup-repair grind -- the longest
    # and most futility-prone of the lot.
    if not cells or not _is_iteration(cells[0]):
        return None
    # A trailing "|" leaves an empty last cell; drop it so the cell count
    # identifies the table.
    if cells[-1] == "":
        cells = cells[:-1]
    return cells


def classify(cells):
    """Which grind a row belongs to, from its shape alone.

    Tracking "the last header seen" is not enough: OpenROAD interleaves
    these tables. `rebuffer` runs *inside* global placement and gpl
    resumes afterwards without reprinting its header, so rows would be
    donated to whichever table printed a header most recently -- quietly
    producing a series that splices two different grinds together.
    """
    n = len(cells)

    def pct(i):
        return i < n and cells[i].endswith("%")

    if n >= 11:
        return "repair_setup"
    if n == 8:
        return "repair_hold"
    if n == 6:
        # repair_design leads with an area percentage; gpl's second cell
        # is the overflow and its fourth is the percentage.
        return "repair_design" if pct(1) else "gpl"
    if n == 5:
        return "rebuffer" if pct(1) else "gpl"
    return None


def _merge_fragments(series):
    """Rejoin one grind that got split across several headers.

    Global placement reprints its header every time a timing-driven
    interruption lands, so a single nesterov run shows up as several
    tables. The iteration counter keeps climbing across the reprint,
    which is what distinguishes a resumed grind from a genuinely new
    one -- a second `repair_design` call restarts its count at 0 and so
    stays separate.
    """
    merged = []
    last_of_kind = {}
    for s in series:
        # The previous grind of this kind, not the previous grind: gpl
        # and rebuffer interleave, so the fragment to rejoin is rarely
        # the one immediately before.
        prev = last_of_kind.get(s.kind)
        resumed = (
            prev is not None
            and prev.kind == s.kind
            and not prev.terminated
            and prev.points
            and s.points
            and s.points[0].iteration > prev.points[-1].iteration
        )
        if resumed:
            prev.points.extend(s.points)
            prev.terminated = s.terminated
            if s.took_s is not None:
                prev.took_s = s.took_s
        else:
            merged.append(s)
            last_of_kind[s.kind] = s
    return merged


def parse_log(text, design="", stage="", log=""):
    """Extract every progress series present in one log file."""
    series = []
    open_series = {}  # kind -> the series rows of that kind currently land in
    gpl_overflow_target = DEFAULT_GPL_OVERFLOW

    def start(kind, metric_name, target):
        s = Series(
            kind=kind,
            design=design,
            stage=stage,
            log=log,
            metric_name=metric_name,
            target=target,
        )
        series.append(s)
        open_series[kind] = s
        return s

    for raw in text.splitlines():
        t, line = unstamp(raw)
        norm = _norm(line)

        m = OVERFLOW_ARG_RE.search(line)
        if m and "global_placement" in line:
            gpl_overflow_target = float(m.group(1))

        # A header opens a new grind of that kind.
        if norm == GPL_HEADER:
            start("gpl", "overflow", gpl_overflow_target)
            continue
        if norm == RD_HEADER:
            start("repair_design", "remaining", 0.0)
            continue
        if norm.startswith("Iter | Removed | Resized"):
            start("repair_setup", "endpoint_tns", 0.0)
            continue
        if norm == RT_HOLD_HEADER:
            start("repair_hold", "viol_endpoints", 0.0)
            continue
        if norm.startswith("Iter | Area | Removed"):
            start("rebuffer", "pins_remaining", 0.0)
            continue

        cells = _row_cells(norm)
        if cells is None:
            m = TOOK_RE.match(norm)
            if m:
                for s in open_series.values():
                    if s.took_s is None:
                        s.took_s = float(m.group(1))
            continue

        kind = classify(cells)
        if kind is None:
            continue
        cur = open_series.get(kind)
        if cur is None:
            # Rows of a table whose header this parser missed.
            cur = start(
                kind,
                "overflow" if kind == "gpl" else "remaining",
                gpl_overflow_target if kind == "gpl" else 0.0,
            )

        pt = _row_from(kind, cells)
        if pt is None:
            continue
        pt.t = t
        if cells[0] == "final":
            cur.terminated = True
            pt.iteration = cur.points[-1].iteration if cur.points else 0
        cur.points.append(pt)

    series = _merge_fragments(series)

    for s in series:
        if not s.points:
            continue
        last = s.points[-1].metric
        if last is not None and last <= s.target:
            s.terminated = True
            s.converged = True
        # repair_setup's endpoint count is worthless as a trajectory but
        # authoritative as a verdict: the final row is the one place it
        # is recomputed. TNS reaching exactly 0.0 is not the flow's own
        # definition of done, so take the verdict from the count.
        if s.kind == "repair_setup":
            viol = s.points[-1].fields.get("viol_endpoints")
            if viol is not None:
                s.converged = viol == 0
    return [s for s in series if s.points]


def _row_from(kind, cells):
    """Turn a table row into a Point, or None if the row is not one."""
    it = _iteration_of(cells[0])

    if kind == "gpl" and len(cells) >= 5:
        return Point(
            iteration=it,
            metric=_num(cells[1]),
            fields={
                "hpwl_um": _num(cells[2]),
                "hpwl_pct": _num(cells[3]),
                "penalty": _num(cells[4]),
            },
        )
    if kind == "repair_design" and len(cells) >= 6:
        return Point(
            iteration=it,
            metric=_num(cells[5]),
            fields={
                "area_pct": _num(cells[1]),
                "resized": _num(cells[2]),
                "buffers": _num(cells[3]),
                "repaired": _num(cells[4]),
            },
        )
    if kind == "repair_setup" and len(cells) >= 11:
        # Endpoint TNS, as a positive quantity falling to zero -- NOT the
        # "Viol Endpts" column, which looks like the obvious progress
        # signal and is not one: it is not recomputed during the run.
        # ibex's grt repair holds it at 719 for all 153 seconds and then
        # prints 0 in the final row, while EnTNS moves -12639 -> -0.2 and
        # WNS -35.8 -> -0.117. Forecasting the frozen column produced a
        # corpus of flat lines and a lot of declined forecasts.
        en_tns = _num(cells[9])
        return Point(
            iteration=it,
            metric=max(-en_tns, 0.0) if en_tns is not None else None,
            fields={
                "removed": _num(cells[1]),
                "resized": _num(cells[2]),
                "inserted": _num(cells[3]),
                "cloned": _num(cells[4]),
                "pin_swaps": _num(cells[5]),
                "area_pct": _num(cells[6]),
                "wns": _num(cells[7]),
                "st_tns": _num(cells[8]),
                "en_tns": _num(cells[9]),
                "viol_endpoints": _num(cells[10]),
            },
        )
    if kind == "rebuffer" and len(cells) >= 5:
        return Point(
            iteration=it,
            metric=_num(cells[4]),
            fields={
                "area_pct": _num(cells[1]),
                "removed": _num(cells[2]),
                "inserted": _num(cells[3]),
            },
        )
    if kind == "repair_hold" and len(cells) >= 8:
        # Hold prints no violating-endpoint count; TNS is the grind metric.
        return Point(
            iteration=it,
            metric=_num(cells[6]),
            fields={
                "resized": _num(cells[1]),
                "buffers": _num(cells[2]),
                "cloned": _num(cells[3]),
                "area": _num(cells[4]),
                "wns": _num(cells[5]),
                "endpoint": cells[7] if len(cells) > 7 else "",
            },
        )
    return None


def parse_file(path, design="", stage=""):
    p = Path(path)
    return parse_log(
        p.read_text(errors="replace"),
        design=design,
        stage=stage,
        log=str(p),
    )


def summarize(series):
    """One line per series: enough to see whether a grind is forecastable."""
    rows = []
    for s in series:
        pts = s.points
        rate = ""
        if pts and pts[0].t is not None and pts[-1].t is not None:
            span = pts[-1].t - pts[0].t
            iters = pts[-1].iteration - pts[0].iteration
            if span > 0 and iters > 0:
                rate = "{:.3f}s/iter".format(span / iters)
        rows.append(
            "{kind:14s} n={n:<5d} {metric}: {first} -> {last} (target {target}) "
            "{term} {took} {rate}".format(
                kind=s.kind,
                n=len(pts),
                metric=s.metric_name,
                first=pts[0].metric,
                last=pts[-1].metric,
                target=s.target,
                term="terminated" if s.terminated else "open",
                took="took={}s".format(s.took_s) if s.took_s else "",
                rate=rate,
            )
        )
    return rows


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    as_json = "--json" in argv
    out = []
    for path in args:
        out.extend(parse_file(path))
    if as_json:
        for s in out:
            print(s.to_json())
    else:
        for row in summarize(out):
            print(row)
        if not out:
            print("no progress series found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
