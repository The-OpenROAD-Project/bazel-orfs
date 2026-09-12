"""Read a place stage's log into the numbers the study compares.

Everything the study measures is already printed by the tools themselves:
the probe's ESTDENSITY_JSON lines, ORFS's own density line, and gpl's
iteration table and warnings. Nothing here re-derives a quantity that a
log already states -- a harvester that computes what the tool reports is
how a study ends up measuring its own arithmetic.

The two questions a log answers:

    what did the estimate say?    -> estimates(), context()
    did global placement get      -> gp_result(): the last iteration's
    where it was aimed?              overflow, and whether gpl warned that
                                     it ran out of iterations or diverged.

Anchors, and why these:

  * ``ESTDENSITY_JSON {...}`` -- written by estimate_probe.tcl; one line
    per overflow target plus one context line.
  * ``Placement density is D, computed from PLACE_DENSITY_LB_ADDON T and
    lower bound U`` -- ORFS's ``place_density_with_lb_addon``. This is the
    density global placement was actually told to use, and the uniform
    density at that moment, which is why the study never has to trust the
    harness's own idea of either.
  * the iteration table, ``iter | overflow | hpwl | ...``, printed by
    gpl's NesterovPlace loop.
  * ``GPL-1010 ... reached the maximum number of iterations`` and
    ``GPL-0998 Divergence detected`` -- the two ways a rung fails to
    arrive. Their absence, plus a final overflow at or under the target,
    is what "converged" means here.
"""

import json
import re

ESTIMATE_PREFIX = "ESTDENSITY_JSON "

# ORFS prints this from a Tcl line continuation, so the whitespace between
# the two halves is whatever the script happened to indent with.
ORFS_DENSITY_RE = re.compile(
    r"Placement density is (?P<density>[0-9.eE+-]+), "
    r"computed from PLACE_DENSITY_LB_ADDON\s+(?P<addon>[0-9.eE+-]+) "
    r"and lower bound (?P<uniform>[0-9.eE+-]+)"
)

# gpl's progress row: "     iter |  overflow |          hpwl | ... ".
# Rows that report a snapshot leave the trailing columns blank, so only
# the first three fields are matched.
GP_ITER_RE = re.compile(
    r"^\s*(?P<iter>\d+)\s*\|\s*(?P<overflow>[0-9.]+)\s*\|"
    r"\s*(?P<hpwl>[0-9.eE+-]+)\s*\|"
)

# gpl warns when its own binary search runs out of iterations and
# returns whatever it had. The value still looks like an answer, so a
# study that does not read this warning would quote a number the tool
# already disowned. The warning is printed by the same call that then
# prints the probe's line, so it belongs to the next estimate.
SEARCH_FAILED_RE = re.compile(r"GPL-0186")

MAX_ITER_RE = re.compile(r"GPL-1010")
DIVERGED_RE = re.compile(r"GPL-0998|Divergence detected")

# The overflow global_placement is asked for. ORFS does not override
# gpl's default, and the probe asks the estimate about the same number.
DEFAULT_OVERFLOW = 0.1


def _estimate_lines(text):
    """The probe's lines, each carrying whether gpl disowned its answer."""
    search_failed = False
    for line in text.splitlines():
        if SEARCH_FAILED_RE.search(line):
            search_failed = True
            continue
        index = line.find(ESTIMATE_PREFIX)
        if index < 0:
            continue
        payload = line[index + len(ESTIMATE_PREFIX):].strip()
        try:
            record = json.loads(payload)
        except ValueError:
            # A truncated log is a broken sample, not a zero.
            raise ValueError("unparseable probe line: " + payload)
        if record.get("kind") == "estimate":
            record["search_converged"] = not search_failed
            search_failed = False
        yield record


def context(text):
    """The probe's context line, or None when the probe did not run."""
    for record in _estimate_lines(text):
        if record.get("kind") == "context":
            return record
    return None


def estimates(text):
    """{overflow: record} for every estimate the probe reported."""
    return {
        float(record["overflow"]): record
        for record in _estimate_lines(text)
        if record.get("kind") == "estimate"
    }


def driven_density(text):
    """The density the probe handed global placement, when it drove it.

    Only the `est` arm has one. It matters because ORFS prints its
    "Placement density is ..." line on the PLACE_DENSITY_LB_ADDON path
    only, so on an arm driven through PLACE_DENSITY the probe's own line
    is the record of what global placement was told.
    """
    for record in _estimate_lines(text):
        if record.get("kind") == "drive":
            return float(record["driven_density"])
    return None


def orfs_density(text):
    """What ORFS told global_placement to use, and the uniform density.

    Returns None for a design driven by a plain PLACE_DENSITY: the line
    only exists on the PLACE_DENSITY_LB_ADDON path, which is the path
    every rung of this study takes.
    """
    match = None
    for line in text.splitlines():
        found = ORFS_DENSITY_RE.search(line)
        if found:
            match = found
    if match is None:
        return None
    return {
        "density": float(match.group("density")),
        "addon": float(match.group("addon")),
        "uniform_density": float(match.group("uniform")),
    }


def gp_result(text, overflow=DEFAULT_OVERFLOW):
    """How global placement ended: did it reach the overflow it aimed at?

    `converged` is deliberately the conjunction of three things rather
    than the last overflow alone: gpl stops early *because* it arrived,
    so a run that ran out of iterations or reverted a divergence can
    still print a plausible-looking last row.
    """
    iterations = []
    for line in text.splitlines():
        match = GP_ITER_RE.match(line.split("] ")[-1])
        if match:
            iterations.append(
                {
                    "iter": int(match.group("iter")),
                    "overflow": float(match.group("overflow")),
                    "hpwl": float(match.group("hpwl")),
                }
            )

    hit_max_iter = bool(MAX_ITER_RE.search(text))
    diverged = bool(DIVERGED_RE.search(text))
    final = iterations[-1] if iterations else None
    return {
        "iterations": len(iterations),
        "final_iter": final["iter"] if final else None,
        "final_overflow": final["overflow"] if final else None,
        "final_hpwl": final["hpwl"] if final else None,
        "hit_max_iter": hit_max_iter,
        "diverged": diverged,
        "target_overflow": overflow,
        "converged": bool(
            final is not None
            and not hit_max_iter
            and not diverged
            and final["overflow"] <= overflow
        ),
        "trajectory": iterations,
    }


# What happens to the netlist between the probe and global placement.
# ORFS puts its PRE_GLOBAL_PLACE hook before `remove_buffers` and
# `buffer_ports`, so the estimate is computed on a slightly different
# design than the one gpl then places. That is a caveat only until it is
# counted, which is what these are for.
BUFFERS_RE = {
    "removed": re.compile(r"RSZ-0026\]?\s*Removed (?P<count>\d+) buffers"),
    "inserted_input": re.compile(
        r"RSZ-0027\]?\s*Inserted (?P<count>\d+) \S+ input buffers"
    ),
    "inserted_output": re.compile(
        r"RSZ-0028\]?\s*Inserted (?P<count>\d+) \S+ output buffers"
    ),
}


def buffer_churn(text):
    """Buffers removed and inserted between the probe and the placer."""
    found = {}
    for key, pattern in BUFFERS_RE.items():
        match = pattern.search(text)
        found[key] = int(match.group("count")) if match else 0
    return found


THREADS_RE = re.compile(r"ORD-0030\]?\s*Using (?P<threads>\d+) thread")


def threads(text):
    """The thread count OpenROAD reported using, or None.

    Stored with every sample so a run whose witness disagrees with the arm
    can be discarded rather than averaged in.
    """
    match = THREADS_RE.search(text)
    return int(match.group("threads")) if match else None


def harvest(text):
    """Everything one rung's log has to say, as one record."""
    return {
        "context": context(text),
        "estimates": estimates(text),
        "orfs_density": orfs_density(text),
        "driven_density": driven_density(text),
        "buffer_churn": buffer_churn(text),
        "gp": gp_result(text),
        "threads": threads(text),
    }
