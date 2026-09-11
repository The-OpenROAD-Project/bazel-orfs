"""Did repair end better than it started, and did it ever go backwards?

`repair_timing -verbose` prints a table, one row per accepted move batch,
carrying WNS, the setup TNS at the start- and end-point of the repair
window, the violating endpoint count and the running move tallies. The
table is the only place the *trajectory* is visible: the stage's metrics
JSON keeps the final values only, so a run that dug itself a hole and
climbed most of the way out is indistinguishable there from one that
walked straight up.

Two questions per table, and they are not the same question:

* **Net** -- is the last row better than the first? A repair that ends
  worse than it started has made the design worse by running, which no
  amount of heuristic search is supposed to do: the resizer keeps a
  journal precisely so a move that does not help can be undone.
* **Excursion** -- did any row go below the first? Recovering does not
  make the excursion free; it is wasted iterations at best, and at worst
  it is the same defect with a luckier ending. Reporting only the net
  hides it, which is why both are computed here.

Measured on `asap7/gcd` at its stock 310 ps clock, the first run taken in
this study went -52.234 ps WNS at row 0 to -55.664 at row 10 -- nine pin
swaps later -- before recovering to -50.325. Net +1.9 ps, excursion
-3.4 ps. That is the shape this screen exists to count across an
ensemble, rather than to marvel at once.

Slacks are read in the units the log prints, which are the design's SDC
units, so every delta here is in those units and is only comparable
within a design.  Sign convention: a delta is `later - earlier` on a
slack, so **positive is better** and negative is a regression.
"""

import re

# The verbose repair table's header, which is what identifies a table in
# a log that also contains repair_design's differently-shaped one. Only
# the columns this screen reads are named; the rest are positional and
# deliberately not depended on beyond their count.
_HEADER = re.compile(r"^\s*Iter\s*\|\s*Removed\s*\|", re.M)

# A data row: the leading iteration number carries a trailing marker
# ('*' while repairing the worst endpoint, '+' during TNS repair) or is
# the literal 'final'. Columns after the marker are separated by '|'.
_ROW = re.compile(
    r"^\s*(?P<iter>\d+|final)(?P<mark>[*+]?)\s*\|"
    r"\s*(?P<removed>\d+)\s*\|"
    r"\s*(?P<resized>\d+)\s*\|"
    r"\s*(?P<inserted>\d+)\s*\|"
    r"\s*(?P<cloned>\d+)\s*\|"
    r"\s*(?P<swaps>\d+)\s*\|"
    r"\s*(?P<area>[-+0-9.]+)%\s*\|"
    r"\s*(?P<wns>[-+0-9.eE]+)\s*\|"
    r"\s*(?P<sttns>[-+0-9.eE]+)\s*\|"
    r"\s*(?P<entns>[-+0-9.eE]+)\s*\|"
    r"\s*(?P<viol>\d+)\s*\|"
    r"\s*(?P<worst>\S*)\s*$",
    re.M,
)

# What repair_timing was asked to do, so a table can be attributed to the
# invocation that produced it rather than to its position in the file.
_INVOCATION = re.compile(r"^\s*(repair_timing[^\n]*)$", re.M)

NUMERIC_COLUMNS = ("area", "wns", "sttns", "entns")
INTEGER_COLUMNS = ("removed", "resized", "inserted", "cloned", "swaps", "viol")


def parse_rows(text):
    """Every repair-table row in a log, in order.

    Args:
        text: the log contents.

    Returns:
        A list of dicts, one per row, with the numeric columns converted
        and `iter` left as a string so the 'final' row keeps its name.
    """
    rows = []
    for match in _ROW.finditer(text):
        row = match.groupdict()
        for column in NUMERIC_COLUMNS:
            row[column] = float(row[column])
        for column in INTEGER_COLUMNS:
            row[column] = int(row[column])
        rows.append(row)
    return rows


def split_tables(text):
    """The log's repair tables, each with the command that produced it.

    A log holds several: `repair_timing` at global route, and the
    `-skip_last_gasp` follow-up that ORFS runs after it. They are
    different questions and must not be pooled.

    Args:
        text: the log contents.

    Returns:
        A list of {"invocation", "rows"} dicts in file order. Tables with
        no parseable rows are dropped -- a header with an empty body
        means repair found nothing to do, which is not a trajectory.
    """
    starts = [match.start() for match in _HEADER.finditer(text)]
    tables = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        body = text[start:end]
        rows = parse_rows(body)
        if not rows:
            continue
        preamble = text[:start]
        invocations = _INVOCATION.findall(preamble)
        tables.append(
            {
                "invocation": invocations[-1].strip() if invocations else None,
                "rows": rows,
            }
        )
    return tables


def summarize(table):
    """Net movement and worst excursion for one repair table.

    Args:
        table: one entry from split_tables().

    Returns:
        A dict per metric (`wns`, `sttns`, `entns`) with `first`, `last`,
        `net` (last - first; positive is better), `excursion` (the most
        negative row - first, so <= 0, and 0 means it never went
        backwards) and `excursion_iter`. Plus the final move tallies and
        `regressed`, the list of metrics whose net is negative -- a list
        rather than a flag because which metric regressed is the whole
        point: WNS improving while endpoint TNS ends worse is a
        different claim from both getting worse, and OR-ing them would
        report the first as the second.

        `excursed` is reported but must not be read as damage. The table
        prints trial states: a row where the pin-swap count *falls*
        relative to the row above it is the resizer's journal restoring
        moves it had just made, so a dip followed by a recovery is the
        search working, not the design being harmed. Measured on
        asap7/gcd seed 21, iteration 10 prints 8 swaps at WNS -53.621 and
        then 3 swaps at -48.060: five swaps tried and rolled back. What
        survives that reading is the **net**, and the counterfactual arm
        (the same seed with SKIP_INCREMENTAL_REPAIR=1) is what turns a
        net into a statement about the design rather than about the
        table.
    """
    rows = table["rows"]
    summary = {"invocation": table["invocation"], "rows": len(rows)}
    regressed = []
    for metric in ("wns", "sttns", "entns"):
        values = [row[metric] for row in rows]
        first, last = values[0], values[-1]
        deltas = [value - first for value in values]
        worst = min(deltas)
        summary[metric] = {
            "first": first,
            "last": last,
            "net": last - first,
            "excursion": worst,
            "excursion_iter": rows[deltas.index(worst)]["iter"],
        }
        if last - first < 0:
            regressed.append(metric)
    final = rows[-1]
    summary["moves"] = {column: final[column] for column in INTEGER_COLUMNS}
    summary["area_percent"] = final["area"]
    summary["regressed"] = regressed
    summary["excursed"] = any(
        summary[metric]["excursion"] < 0 for metric in ("wns", "sttns", "entns")
    )
    return summary


def summarize_log(text):
    """Every repair table in one stage log, summarized.

    Args:
        text: the log contents.

    Returns:
        A list of summaries, one per table, in file order.
    """
    return [summarize(table) for table in split_tables(text)]
