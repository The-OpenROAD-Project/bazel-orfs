#!/usr/bin/env python3
"""Split an ORFS substep log into the phases that consumed its time.

A stage is not the tool it is named after. `5_1_grt` spends most of its
time in `repair_timing` and `pin_access`; FastRoute itself is a few
percent. Comparing thread counts at substep granularity therefore
averages regions that want *opposite* thread counts -- global route's
maze loops are `schedule(static)` over memory-bound work, while
detailed route's and pin access's are `schedule(dynamic)` over irregular
tasks -- and the average is not a policy.

Nothing here is instrumentation. ORFS and OpenROAD already write the
breakdown; this reads it:

    Took 34 seconds: pin_access
    Took 13 seconds: global_route
    Took 120 seconds: repair_timing -setup_margin 0 ... -verbose
    [INFO RSZ-0505] Runtime: 119.68s
    [INFO RSZ-0506] Runtime: 0.22s

`Took` lines come from ORFS's util.tcl and bound one flow command each,
so they do not overlap and can be summed. A `Runtime:` line may or may
not already be inside one, and that is decided per line: RSZ-0505 sits
within `Took ... repair_timing`, so counting both double counts the same
seconds; but repair_design reports RSZ-0504 with no `Took` line of its
own, and `4_1_cts` has no `Took` lines at all, so there its CTS-0500 is
the only attribution available. Enclosure is therefore tested against
the span each `Took` covers -- from the command echo to the `Took` line
-- rather than by "the next Took wins", which would file repair_design's
seconds under repair_timing.

With `RUN_CMD` pointed at log_timestamps.py every line also carries
elapsed seconds, which locates each phase in the run and bounds the
phases that have no `Took` line of their own.

The remainder is reported as *unattributed* rather than distributed.
A phase stack that does not add up to the substep's wall time is a
mis-parse, and the caller is meant to see that instead of a total that
was quietly made to balance.
"""

import re

# An elapsed stamp from log_timestamps.py: "[  184.421] ".
# re.M matters: elapsed_span() scans the whole text with findall, and
# without it `^` anchors only to position 0 and every span reads as None.
_STAMP = re.compile(r"^\[\s*(\d+(?:\.\d+)?)\]\s?", re.M)

# ORFS util.tcl, optionally behind an elapsed stamp. One flow command.
_TOOK = re.compile(
    r"^(?:\[\s*\d+(?:\.\d+)?\]\s?)?Took (\d+) seconds: (\S+)(.*)$"
)

# A tool reporting its own runtime, e.g. "[INFO RSZ-0505] Runtime: 119.68s".
# Nested inside whichever Took phase encloses it.
_RUNTIME = re.compile(
    r"^(?:\[\s*\d+(?:\.\d+)?\]\s?)?\[INFO ([A-Z]+)-(\d+)\] Runtime: "
    r"(\d+(?:\.\d+)?)s\s*$",
    re.M,
)


def is_stamped(text):
    """True if the log carries log_timestamps.py elapsed prefixes.

    Checked rather than assumed: a campaign that believes it enabled
    RUN_CMD and did not would otherwise report every phase as
    unattributed and look like a parser bug.
    """
    for line in text.splitlines():
        if _STAMP.match(line):
            return True
    return False


def elapsed_span(text):
    """Last minus first elapsed stamp, or None when unstamped."""
    stamps = _STAMP.findall(text)
    if len(stamps) < 2:
        return None
    return float(stamps[-1]) - float(stamps[0])


def _strip_stamp(line):
    return _STAMP.sub("", line)


def parse_phases(text):
    """The phase stack of one substep log.

    Returns a dict with:
      phases:       top-level, non-overlapping. Each is
                    {name, seconds, detail, order, source}. `name`
                    repeats when a command runs twice (global_route.tcl
                    calls repair_timing twice), so `order` distinguishes
                    them.
      nested:       `Runtime:` lines that fall inside a `Took` span, so
                    already counted by it. NOT added to the total.
      attributed_s: sum of `phases`.
      stamped/span_s: elapsed-stamp presence and range.

    Two sources, and which one applies is decided per line rather than
    per log, because both shapes occur:

      * `Took N seconds: <cmd>` (ORFS util.tcl) spans from where <cmd>
        was echoed to the Took line. `5_1_grt` has three of these.
      * `[INFO XXX-nnnn] Runtime: N s` from inside a tool. Some fall
        inside a Took span -- RSZ-0505 sits within `Took ...
        repair_timing` -- and counting both double counts the same
        seconds. Others do not: repair_design reports RSZ-0504 with no
        Took line of its own, and `4_1_cts` has no Took lines at all,
        so its CTS-0500 is the only attribution there is.

    So enclosure is tested by span, not by "the next Took wins". That
    naive rule would file repair_design's 3.47s inside repair_timing,
    which is the wrong region and the wrong policy conclusion.
    """
    lines = text.splitlines()
    bare = [_strip_stamp(l) for l in lines]

    # Took phases, with the span each one covers.
    phases = []
    spans = []
    for order, (idx, line) in enumerate(
        [(i, b) for i, b in enumerate(bare) if _TOOK.match(b)]
    ):
        match = _TOOK.match(line)
        name = match.group(2)
        detail = match.group(3).strip()
        # The command echo: the last preceding line that is the command
        # itself. Exact match first, then a prefix match, then give up
        # and treat the phase as covering only its own line.
        echo = idx
        target = (name + " " + detail).strip()
        for back in range(idx - 1, -1, -1):
            candidate = bare[back].strip()
            if candidate == target or (detail and candidate.startswith(target)):
                echo = back
                break
        else:
            for back in range(idx - 1, -1, -1):
                if bare[back].strip().startswith(name):
                    echo = back
                    break
        spans.append((echo, idx))
        phases.append(
            {
                "name": name,
                "seconds": float(match.group(1)),
                "detail": detail,
                "order": order,
                "source": "took",
            }
        )

    def inside_a_span(i):
        return any(lo <= i <= hi for lo, hi in spans)

    nested = []
    for idx, line in enumerate(bare):
        match = _RUNTIME.match(line)
        if not match:
            continue
        record = {
            "tool": match.group(1),
            "code": match.group(2),
            "seconds": float(match.group(3)),
        }
        if inside_a_span(idx):
            nested.append(record)
        else:
            # No Took line covers this one, so it is the best available
            # attribution rather than a duplicate.
            phases.append(
                {
                    "name": "{}-{}".format(record["tool"], record["code"]),
                    "seconds": record["seconds"],
                    "detail": "tool runtime, no enclosing Took line",
                    "order": len(phases),
                    "source": "runtime",
                }
            )

    return {
        "phases": phases,
        "nested": nested,
        "attributed_s": sum(p["seconds"] for p in phases),
        "stamped": is_stamped(text),
        "span_s": elapsed_span(text),
    }


def reconcile(parsed, wall_s, tolerance_s=1.0, tolerance_frac=0.05):
    """Does the phase stack account for the substep's wall time?

    `Took` reports whole seconds, so a stack of k phases can be off by
    up to k seconds from rounding alone; the tolerance is therefore both
    absolute and proportional. Returns a dict with the remainder and an
    `ok` flag -- never adjusts the numbers to fit.

    Over-attribution (attributed > wall) is its own failure and is
    reported as a negative remainder rather than clamped: it means two
    phases were counted that overlap, which is a parser bug and not a
    measurement.
    """
    attributed = parsed["attributed_s"]
    unattributed = wall_s - attributed
    allowed = max(tolerance_s * max(1, len(parsed["phases"])),
                  tolerance_frac * wall_s)
    return {
        "wall_s": wall_s,
        "attributed_s": attributed,
        "unattributed_s": unattributed,
        "over_attributed": unattributed < -allowed,
        "ok": unattributed >= -allowed,
        "allowed_s": allowed,
    }


def by_name(parsed):
    """Phase seconds summed per command name, for cross-arm comparison."""
    totals = {}
    for phase in parsed["phases"]:
        totals[phase["name"]] = totals.get(phase["name"], 0.0) + phase["seconds"]
    return totals
