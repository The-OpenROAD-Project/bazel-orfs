"""The Nesterov descent, reduced to the two numbers this study compares.

Global placement prints a progress table -- `Iteration | Overflow |
HPWL (um) | HPWL(%) | Penalty | Group` -- and prints it *again* after
every timing-driven interruption, because `repair_design` changes the
netlist underneath the optimizer and the descent restarts against a new
objective. So a stage log holds one table per segment, and the last row
of the last table is where the placement actually ended up.

Two columns are the study's primary endpoints, and both come from here:

* **`hpwl_final`** -- what global placement is optimizing. One step from
  the change under test, where `min_period` at global route is four, so
  it carries far less of the flow's noise. Measured over PR #977's 402
  samples its 2-sigma spread is 0.65%-2.81% of the mean.

* **`iterations`** -- a runtime proxy that does not depend on the
  machine. Wall time can only be compared between samples run one at a
  time on an idle host; an iteration count can be compared between
  samples run several-wide. On #977's ensembles it is near-deterministic
  -- aes and ethmac produced the *same* count across all 16 seeds -- so
  it resolves a runtime difference at a fraction of the samples wall
  time would need.

Column names match PR #977's raw CSV (`gp_hpwl_final`, `gp_iterations`,
`diverge_revert`) so the two studies' samples can be pooled rather than
merely compared.
"""

import re

# HPWL is printed in um in scientific notation. The percent column is
# the change against the previously *printed* row, not across a segment,
# so it is parsed but never used for a conclusion.
_PROGRESS_ROW = re.compile(
    r"^\s*(?P<iteration>\d+)\s*\|"
    r"\s*(?P<overflow>[0-9.]+)\s*\|"
    r"\s*(?P<hpwl>[0-9.eE+-]+)\s*\|",
    re.M,
)

_TABLE_HEADER = re.compile(r"^Iteration \| Overflow \|", re.M)

_DIVERGE_REVERT = re.compile(r"Divergence detected, reverting to snapshot")
_DIVERGE_FATAL = re.compile(r"RePlAce divergence detected")
_NESTEROV_START = re.compile(r"Execute Nesterov Global Placement")


def rows(text):
    """Every progress row in the log, in order.

    Args:
        text: a `3_3_place_gp.log`.

    Returns:
        A list of {iteration, overflow, hpwl} dicts. Rows from every
        segment are concatenated; `segments()` says where the seams are.
    """
    out = []
    for match in _PROGRESS_ROW.finditer(text):
        out.append(
            {
                "iteration": int(match.group("iteration")),
                "overflow": float(match.group("overflow")),
                "hpwl": float(match.group("hpwl")),
            }
        )
    return out


def segments(text):
    """How many times the descent restarted.

    Args:
        text: a `3_3_place_gp.log`.

    Returns:
        The number of progress tables, which is one more than the number
        of timing-driven interruptions. Reported because an arm that
        changes how often `repair_design` fires has changed the shape of
        the run, not just its endpoint, and two arms with different
        segment counts are not comparing like with like.
    """
    return len(_TABLE_HEADER.findall(text))


def summarize(text):
    """The descent's endpoint and shape.

    Args:
        text: a `3_3_place_gp.log`.

    Returns:
        A dict, or None when no progress table is present -- a run that
        was given `-skip_nesterov_place`, or one that died first.

        * `iterations`     the last iteration number reached
        * `rows`           how many rows were printed
        * `hpwl_final`     last HPWL, in um
        * `hpwl_first`     first HPWL, in um
        * `overflow_final` last overflow
        * `segments`       progress tables
        * `diverge_revert` the placer reverted to a snapshot
        * `diverge_fatal`  the placer declared divergence
        * `ran`            Nesterov was entered at all
    """
    progress = rows(text)
    if not progress:
        return None
    last = progress[-1]
    return {
        "iterations": last["iteration"],
        "rows": len(progress),
        "hpwl_final": last["hpwl"],
        "hpwl_first": progress[0]["hpwl"],
        "overflow_final": last["overflow"],
        "segments": segments(text),
        "diverge_revert": bool(_DIVERGE_REVERT.search(text)),
        "diverge_fatal": bool(_DIVERGE_FATAL.search(text)),
        "ran": bool(_NESTEROV_START.search(text)),
    }
