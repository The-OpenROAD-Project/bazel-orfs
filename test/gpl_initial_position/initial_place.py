"""What the conjugate-gradient initial place did, read from the stage log.

Three things are recoverable from an ORFS `3_3_place_gp.log` with no
instrumentation at all, and one more with the study patch:

1. **The convergence trajectory.** `doBicgstabPlace()` prints
   `[InitialPlace]  Iter: N conjugate gradient residual: R HPWL: H` once
   per outer iteration, and breaks out when `R <= 1e-5 && N >= 5`
   against a cap of `-initial_place_max_iter` (default 20).

2. **Where the instances started, on the shipped path.** `GPL-0051`
   prints the three counters `placeInstsInitialPositions()` keeps: how
   many instances took an ODB location, the core center, and a region
   center.

3. **Whether the solve gave up.** `GPL-0325` warns on a NaN residual.

4. **Which arm actually ran**, from the study patch's own line. An arm
   is only credited when its log names the mode it was supposed to run
   under; a sample whose witness disagrees is discarded rather than
   averaged in.

## Why the trajectory is the first thing this study reads

The start position is the initial guess of an iterative solve whose
matrix is re-linearised from the current positions on every outer
iteration. If the loop converges, the guess washes out and the policy
cannot matter through initial place at all; if it hits the cap, the
guess is a free parameter carried into Nesterov. Which regime a design
is in is therefore a precondition for interpreting any QoR number here,
and it costs nothing to read.
"""

import re

# `log_->report("[InitialPlace]  Iter: {} conjugate gradient residual: "
#               "{:0.8f} HPWL: {}", ...)` -- two spaces after the tag.
_CG_ITER = re.compile(
    r"\[InitialPlace\]\s+Iter:\s*(?P<iteration>\d+)\s+"
    r"conjugate gradient residual:\s*(?P<residual>[-+0-9.eEnan]+)\s+"
    r"HPWL:\s*(?P<hpwl>\d+)"
)

# GPL-0051, the shipped path's own counters. The message is emitted as
# one string with embedded tabs, so the three counts may land on one
# line or several depending on the log formatter; match each
# independently rather than assuming a layout.
_SRC_ODB = re.compile(r"Odb location\s*=\s*(?P<count>\d+)")
_SRC_CORE = re.compile(r"Core center\s*=\s*(?P<count>\d+)")
_SRC_REGION = re.compile(r"Region center\s*=\s*(?P<count>\d+)")

# The study patch's witness line.
_MODE = re.compile(
    r"\[InitialPlace\]\s+initial_position_mode\s+(?P<mode>\w+):\s*"
    r"placed\s+(?P<placed>\d+)\s+instances\s*"
    r"\(region box\s+(?P<region>\d+),\s*"
    r"odb location\s+(?P<odb>\d+),\s*"
    r"anchored\s+(?P<anchored>\d+)\),\s*seed\s+(?P<seed>\d+)"
)

_CG_START = re.compile(r"Execute Conjugate Gradient Initial Placement")
_CG_NAN = re.compile(r"GPL-0325\]")

# `doBicgstabPlace()`: `if (error_max <= 1e-5 && iter >= 5) break;`
CONVERGENCE_RESIDUAL = 1e-5
CONVERGENCE_MIN_ITER = 5


def _to_float(text):
    """A residual, or None when the solver printed a NaN.

    Args:
        text: the captured residual field.

    Returns:
        The value, or None. NaN is deliberately not returned as a float:
        it compares false against every threshold, so a caller that
        forgot to check would silently read it as "did not converge"
        when the truthful answer is "the solve failed".
    """
    try:
        value = float(text)
    except ValueError:
        return None
    if value != value:
        return None
    return value


def trajectory(text):
    """The initial-place outer loop, iteration by iteration.

    Args:
        text: a `3_3_place_gp.log` (or `3_1_place_gp_skip_io.log`).

    Returns:
        A list of {iteration, residual, hpwl} dicts, in log order.
        Empty when initial place did not run -- which is itself a
        finding, since `-skip_initial_place` and
        `-initial_place_max_iter 0` both produce it.
    """
    out = []
    for match in _CG_ITER.finditer(text):
        out.append(
            {
                "iteration": int(match.group("iteration")),
                "residual": _to_float(match.group("residual")),
                "hpwl": int(match.group("hpwl")),
            }
        )
    return out


def convergence(text, max_iter=20):
    """Did the initial-place solve converge, or did it run out of room?

    Args:
        text: a place stage log.
        max_iter: the `-initial_place_max_iter` the run used, so a
            design that stopped at the cap is distinguished from one
            that stopped because it was finished.

    Returns:
        A dict, or None when initial place did not run:

        * `iterations`      how many outer iterations were printed
        * `final_residual`  the last residual, or None on a NaN
        * `converged`       the break condition actually fired
        * `hit_cap`         it stopped because it ran out of iterations
        * `nan`             the solver reported a NaN residual
        * `hpwl_first` / `hpwl_last`

        `converged` and `hit_cap` are both reported rather than derived
        from each other: a run can print exactly `max_iter` iterations
        *and* meet the residual on the last one, and calling that
        "capped" would overstate how free the starting point is.
    """
    rows = trajectory(text)
    if not rows:
        return None
    last = rows[-1]
    residual = last["residual"]
    converged = (
        residual is not None
        and residual <= CONVERGENCE_RESIDUAL
        and last["iteration"] >= CONVERGENCE_MIN_ITER
    )
    return {
        "iterations": len(rows),
        "last_iteration": last["iteration"],
        "final_residual": residual,
        "converged": converged,
        "hit_cap": last["iteration"] >= max_iter and not converged,
        "nan": bool(_CG_NAN.search(text)) or residual is None,
        "hpwl_first": rows[0]["hpwl"],
        "hpwl_last": last["hpwl"],
        "ran": bool(_CG_START.search(text)),
    }


def position_sources(text):
    """The GPL-0051 counters, when the shipped path ran.

    Args:
        text: a place stage log.

    Returns:
        {odb, core_center, region_center}, or None when the line is
        absent -- which is the case for every arm that ran under
        `-initial_position_mode`, since that path reports its own
        witness instead.
    """
    odb = _SRC_ODB.search(text)
    core = _SRC_CORE.search(text)
    region = _SRC_REGION.search(text)
    if not (odb and core and region):
        return None
    return {
        "odb": int(odb.group("count")),
        "core_center": int(core.group("count")),
        "region_center": int(region.group("count")),
    }


def mode_witness(text):
    """The arm this log actually ran, from the study patch's own line.

    Args:
        text: a place stage log.

    Returns:
        {mode, placed, region, odb, anchored, seed}, or None when the
        run took the shipped path.
    """
    match = _MODE.search(text)
    if not match:
        return None
    return {
        "mode": match.group("mode"),
        "placed": int(match.group("placed")),
        "region": int(match.group("region")),
        "odb": int(match.group("odb")),
        "anchored": int(match.group("anchored")),
        "seed": int(match.group("seed")),
    }


def witnessed_arm(text):
    """The arm name a log attests to, independent of what it was asked.

    The campaign labels a sample from the command it issued; this reads
    the label back out of the run. They are compared, and a sample where
    they disagree is dropped. Without this an arm whose flag was
    silently ignored -- a misspelled mode, an ORFS variable that did not
    reach the command line -- reads as "this distribution behaves
    exactly like the default", which is the one wrong answer that looks
    like a result.

    Args:
        text: a place stage log.

    Returns:
        The mode name, `"shipped"` when the GPL-0051 path ran, or None
        when neither witness is present.
    """
    witness = mode_witness(text)
    if witness:
        return witness["mode"]
    if position_sources(text) is not None:
        return "shipped"
    return None
