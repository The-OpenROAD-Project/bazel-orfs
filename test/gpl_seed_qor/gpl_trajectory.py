"""The Nesterov trajectory, and the divergence signature that hides in it.

Timing-driven global placement is not one descent: it is a descent that
is interrupted, one or more times, by a `repair_design` call that
creates, deletes and resizes instances underneath the optimizer. The log
prints the progress table (`Iteration | Overflow | HPWL (um) | ...`)
once per segment and a GPL-0100..0110 block at each interruption, so the
whole shape is recoverable from the stage log with no instrumentation.

## Why the shape matters

OpenROAD #11385 -- "gpl: Wrong buffer placement during timing-driven
GPL", open as of 2026-09-10 -- reports that the placer reseeds only the
instances `repair_design` created while keeping the accelerated-gradient
coefficient and the existing cell velocities, so it carries momentum
from before the interruption onto an objective that changed. The run
diverges in the sense that matters (buffers end up thousands of microns
from their drivers) while `isDiverged()` stays quiet, because **HPWL
grows while overflow falls** and nothing was watching that pair.

That is a signature, not a diagnosis, and this module computes it for
every run rather than arguing about it: per post-repair segment, the
change in HPWL against the change in overflow. A seed ensemble then
turns it into a rate -- how often a trajectory does this on designs
other than the one in the issue -- and the grt timing of the same run
says what it cost.

The threshold is an argument with a default, and the raw per-segment
numbers are always reported, so a reader can move the line without
re-running anything.
"""

import re

# Progress-table row. HPWL is printed in um in scientific notation; the
# percent column is the change against the previous printed row, which
# is not the same as the change across a segment, so it is kept but not
# used for the signature.
_PROGRESS_ROW = re.compile(
    r"^\s*(?P<iteration>\d+)\s*\|"
    r"\s*(?P<overflow>[0-9.]+)\s*\|"
    r"\s*(?P<hpwl>[0-9.eE+-]+)\s*\|"
    r"\s*(?P<hpwl_percent>[-+0-9.]+)%\s*\|"
    r"\s*(?P<penalty>[0-9.eE+-]+)\s*\|",
    re.M,
)

# The timing-driven interruption block. GPL-0101 is the state at the
# moment of the call; 0106-0110 are what repair_design did to the
# netlist and what gpl did with its density target afterwards.
_TD_START = re.compile(
    r"GPL-0100\]\s*Timing-driven iteration (?P<index>\d+)/(?P<total>\d+),"
    r"\s*virtual:\s*(?P<virtual>\w+)"
)
_TD_STATE = re.compile(
    r"GPL-0101\]\s*Iter:\s*(?P<iteration>\d+),\s*overflow:\s*(?P<overflow>[0-9.]+),"
    r"[^,]*,\s*HPWL:\s*(?P<hpwl>\d+)"
)
_TD_SLACK = re.compile(r"GPL-0106\]\s*Timing-driven: worst slack\s*(?P<slack>[-+0-9.eE]+)")
_TD_AREA = re.compile(
    r"GPL-0107\].*?delta area:\s*(?P<area>[-0-9.]+) um\^2 "
    r"\((?P<percent>[-+0-9.]+)%\)"
)
_TD_GCELLS = re.compile(
    r"GPL-0109\].*?created:\s*(?P<created>\d+),\s*deleted:\s*(?P<deleted>\d+)"
)
_TD_DENSITY = re.compile(r"GPL-0110\].*?density:\s*(?P<density>[0-9.]+)")

# What the placer itself says about divergence, so a run that was caught
# is never counted as a run that was missed.
_DIVERGED_REGIONS = re.compile(r"Divergence occured in (?P<regions>\d+) regions")
_DIVERGE_REVERT = re.compile(r"Divergence detected, reverting to snapshot")
_DIVERGE_FATAL = re.compile(r"RePlAce divergence detected")

# Chesterton's Fence, and the reason the obvious screen is wrong: HPWL
# rising while overflow falls is what a *healthy* Nesterov descent does.
# The spreading force buys legality with wirelength, so every run trades
# one for the other. Measured on asap7/gcd, the descent before any
# interruption pays +23.5% HPWL for -0.418 of overflow. Flagging that
# would flag every design ever placed.
#
# What #11385 describes is not the trade but its *price*: +145% HPWL,
# with buffers thousands of microns from their drivers. So the screen is
# the exchange rate -- HPWL growth per unit of overflow bought.
#
# What it is priced against is the ensemble, not the run. The obvious
# per-run baseline, the descent before the first interruption, does not
# exist on real designs: on asap7/gcd the first GPL-0100 fires at
# iteration 1, so there is no pre-repair trajectory to normalise by. The
# seeds supply what the run cannot -- the same design placed N ways, of
# which one may be the outlier -- which is precisely the thing a single
# run could never give and this campaign exists to have.
#
# So this module parses and rates; it does not decide. flag() takes the
# baseline the caller derived from the ensemble, and every segment's raw
# numbers are reported whether or not they are flagged.
EXCHANGE_RATIO = 3.0
HPWL_GROWTH = 0.25


def parse_progress(text):
    """Every Nesterov progress row in the log, in order.

    Args:
        text: the place-stage log contents.

    Returns:
        A list of dicts with `iteration`, `overflow`, `hpwl` (um) and
        `penalty`. Rows from the resizer's and detailed placer's own
        tables cannot match: theirs have different column counts and
        carry a '%' where this one carries a bare overflow.
    """
    rows = []
    for match in _PROGRESS_ROW.finditer(text):
        rows.append(
            {
                "iteration": int(match.group("iteration")),
                "overflow": float(match.group("overflow")),
                "hpwl": float(match.group("hpwl")),
                "penalty": float(match.group("penalty")),
            }
        )
    return rows


def parse_td_events(text):
    """The timing-driven interruptions, with what repair_design did.

    Args:
        text: the place-stage log contents.

    Returns:
        A list of dicts in log order, one per GPL-0100 block, carrying
        the placement state at the call and the netlist delta. Fields
        absent from the log (an interruption that printed no area line,
        say) are None rather than guessed.
    """
    events = []
    for match in _TD_START.finditer(text):
        tail = text[match.end() : match.end() + 4000]
        state = _TD_STATE.search(tail)
        slack = _TD_SLACK.search(tail)
        area = _TD_AREA.search(tail)
        gcells = _TD_GCELLS.search(tail)
        density = _TD_DENSITY.search(tail)
        events.append(
            {
                "index": int(match.group("index")),
                "total": int(match.group("total")),
                "virtual": match.group("virtual") == "true",
                "iteration": int(state.group("iteration")) if state else None,
                "overflow": float(state.group("overflow")) if state else None,
                "hpwl": float(state.group("hpwl")) if state else None,
                "worst_slack": float(slack.group("slack")) if slack else None,
                "area_percent": float(area.group("percent")) if area else None,
                "gcells_created": int(gcells.group("created")) if gcells else None,
                "gcells_deleted": int(gcells.group("deleted")) if gcells else None,
                "target_density": float(density.group("density")) if density else None,
            }
        )
    return events


def segments(rows, events):
    """Split the trajectory at the timing-driven interruptions.

    Args:
        rows: parse_progress() output.
        events: parse_td_events() output.

    Returns:
        A list of {"after_repair", "rows"} dicts. The first segment is
        the descent before any interruption (`after_repair` None); each
        later one carries the index of the GPL-0100 block that preceded
        it, so a segment can be attributed to the repair that changed
        the objective under it.
    """
    boundaries = [
        event["iteration"] for event in events if event["iteration"] is not None
    ]
    out = []
    current = {"after_repair": None, "rows": []}
    remaining = list(enumerate(boundaries))
    for row in rows:
        while remaining and row["iteration"] > remaining[0][1]:
            index, _ = remaining.pop(0)
            if current["rows"]:
                out.append(current)
            current = {"after_repair": index, "rows": []}
        current["rows"].append(row)
    if current["rows"]:
        out.append(current)
    return out


def exchange_rate(delta):
    """HPWL growth per unit of overflow bought, for one segment.

    Args:
        delta: one entry of the per-segment list built by signature().

    Returns:
        The rate, or None when the segment bought no overflow at all --
        a segment that raised HPWL while overflow also rose has no
        exchange rate, and is reported through `overflow_delta` instead
        rather than as an infinity.
    """
    bought = -delta["overflow_delta"]
    if bought <= 0:
        return None
    return delta["hpwl_growth"] / bought


def signature(text):
    """Parse one place-stage log into a rated trajectory.

    Args:
        text: the place-stage log contents.

    Returns:
        A dict with `segments` (each carrying its HPWL and overflow
        deltas and its `exchange_rate`), `td_events`, and what the
        placer itself said about divergence. Nothing is flagged here:
        what counts as an outlying rate is an ensemble question, and
        flag() answers it with a baseline the caller supplies.
    """
    rows = parse_progress(text)
    events = parse_td_events(text)
    deltas = []
    for segment in segments(rows, events):
        body = segment["rows"]
        if len(body) < 2:
            continue
        first, last = body[0], body[-1]
        peak = max(row["hpwl"] for row in body)
        delta = {
            "after_repair": segment["after_repair"],
            "iterations": [first["iteration"], last["iteration"]],
            "hpwl_first": first["hpwl"],
            "hpwl_last": last["hpwl"],
            "hpwl_peak": peak,
            "hpwl_growth": last["hpwl"] / first["hpwl"] - 1.0,
            "hpwl_peak_growth": peak / first["hpwl"] - 1.0,
            "overflow_first": first["overflow"],
            "overflow_last": last["overflow"],
            "overflow_delta": last["overflow"] - first["overflow"],
        }
        delta["exchange_rate"] = exchange_rate(delta)
        deltas.append(delta)

    regions = _DIVERGED_REGIONS.search(text)
    return {
        "td_events": events,
        "segments": deltas,
        "diverged_regions": int(regions.group("regions")) if regions else 0,
        "diverge_revert": bool(_DIVERGE_REVERT.search(text)),
        "diverge_fatal": bool(_DIVERGE_FATAL.search(text)),
        "final_hpwl": rows[-1]["hpwl"] if rows else None,
        "final_overflow": rows[-1]["overflow"] if rows else None,
        "iterations": rows[-1]["iteration"] if rows else None,
    }


def flag(segments_, baseline_rate, exchange_ratio=EXCHANGE_RATIO,
         hpwl_growth=HPWL_GROWTH):
    """Which post-repair segments paid an outlying price for legality.

    Args:
        segments_: the `segments` list from signature().
        baseline_rate: the ensemble's typical exchange rate for this
            design -- a median over every post-repair segment of every
            seed, so one bad run cannot set its own bar. None disables
            flagging, which is how a design with too few runs reports
            "not yet measured" instead of a made-up verdict.
        exchange_ratio: how many times the baseline counts as outlying.
        hpwl_growth: absolute floor, so a short segment with a noisy
            rate cannot flag on ratio alone.

    Returns:
        The flagged segments, in order.
    """
    if baseline_rate is None or baseline_rate <= 0:
        return []
    flagged = []
    for delta in segments_:
        if delta["after_repair"] is None:
            continue
        if delta["hpwl_growth"] < hpwl_growth:
            continue
        rate = delta["exchange_rate"]
        # Buying no overflow at all while HPWL grows is worse than a bad
        # rate, not better, so it flags on the growth floor alone.
        if rate is None or rate >= exchange_ratio * baseline_rate:
            flagged.append(delta)
    return flagged
