#!/usr/bin/env python3
"""What proves two arms did, or did not, produce the same thing.

#968 compared one witness: a sha1 of the substep's `.odb`. For a
*runtime* study that is enough -- it only has to establish that the arms
did the same work before their times are compared. For an idempotency
study it is not, because it can miss a divergence in both directions:

1. **The ODB does not carry everything a stage writes.** Each stage also
   writes an `.sdc`, and `@openroad//test/orfs:check_same.sh` -- the
   comparator `gcd_single_flow` uses at all seven stage boundaries --
   compares the `.sdc` *first*, deliberately: a binary ODB diff stops at
   the first differing byte and tells a reader nothing, while an `.sdc`
   diff is readable.

2. **A divergence can be repaired away.** STA can hand rsz a different
   answer at 16 threads than at 1, rsz can buffer until both close, and
   the resulting ODB can land identical. That is still the class-1 bug
   the campaign is hunting -- and the ORFS metrics ORFS already writes
   per substep record enough to see it: worst slack, TNS, clock skew,
   how many setup and hold buffers were inserted.

So three witnesses, each answering a different question, and none of
them new instrumentation: `.odb` bytes, `.sdc` bytes, and the subset of
ORFS's own `report_metrics` JSON that a divergence would move.

The metric subset is curated rather than whole. The full JSON carries
runtime and peak-memory fields that differ between two runs of
identical work, so comparing all of it would report every pair of arms
as divergent -- the failure mode #968 hit and documented, a fake QoR
divergence across 48 of 54 design/substep pairs.
"""

import hashlib
import json
import os

# The metric keys a thread-count divergence would move, matched on
# suffix so the same list serves every stage (ORFS prefixes each key
# with the stage: `cts__timing__setup__ws`).
#
# Timing first, because that is what STA computes and what a class-1
# bug perturbs. Then the buffer counts, which are rsz's own output and
# the exact signal in OpenROAD#9781. Then size and wirelength, which
# move when a different decision was taken. Deliberately absent:
# anything with `runtime` or `power` in it -- runtime differs between
# identical runs by definition, and power is derived from an activity
# annotation this flow does not fix.
QOR_SUFFIXES = (
    "__timing__setup__ws",
    "__timing__setup__tns",
    "__timing__hold__ws",
    "__timing__hold__tns",
    "__timing__fmax",
    "__clock__skew__setup",
    "__clock__skew__hold",
    "__timing__drv__setup_violation_count",
    "__timing__drv__hold_violation_count",
    "__timing__drv__max_slew",
    "__timing__drv__max_cap",
    "__timing__drv__max_fanout",
    "__design__instance__count__setup_buffer",
    "__design__instance__count__hold_buffer",
    "__design__instance__count",
    "__design__instance__area",
    "__design__nets",
    "__design__violations",
    "__route__wirelength",
    "__route__wirelength__estimated",
    # The route substep runs no STA, so none of the timing keys above
    # exist there: its metrics are drt's own counts. Without these,
    # `5_2_route` compared one key (wirelength) and `5_3_fillcell`
    # compared none, and both reported `stable` while comparing
    # nothing -- the exact quiet-wrong-data failure this file's
    # docstring warns about, found by looking at a real route sample
    # rather than by a test.
    "__route__drc_errors",
    "__route__net",
    "__route__net__special",
    "__route__vias",
    "__route__vias__multicut",
    "__route__vias__singlecut",
    "__antenna__violating__nets",
    "__antenna__violating__pins",
    "__antenna_diodes_count",
    # A change in how many errors or warnings a substep emitted is a
    # divergence, whatever else agreed. The per-message
    # `flow__warnings__count:STA-0450` keys ride along on the same
    # suffix and are as deterministic as the totals.
    "__flow__errors__count",
    "__flow__warnings__count",
)

# The three witnesses, in the order they are worth reading. `sdc`
# before `odb` for check_same.sh's reason: it is the one a human can
# diff.
KINDS = ("sdc", "odb", "qor")


def sha1_prefix(path):
    """The first 20 hex characters of a file's sha1, or None.

    Twenty is what ORFS's own `genElapsedTime.py` summary row uses, so
    a witness computed here and one read from a log stay comparable.
    """
    if not path or not os.path.exists(path):
        return None
    hasher = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:20]


def odb_sha1(results, step):
    """The substep's own `.odb`."""
    return sha1_prefix(os.path.join(results, step + ".odb"))


def sdc_sha1(results, sdc_name):
    """The stage's `.sdc`, named by STAGE_METADATA's result_names."""
    if not sdc_name:
        return None
    return sha1_prefix(os.path.join(results, sdc_name))


def qor(logs, step):
    """The comparable subset of ORFS's metrics for one substep.

    Keys are returned with the stage prefix stripped, so the same
    column names read across stages. Returns None when the substep
    wrote no metrics -- distinct from `{}`, which would mean it wrote
    metrics and none of them were comparable.
    """
    path = os.path.join(logs, step + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as handle:
            metrics = json.load(handle)
    except ValueError:
        return None
    if not isinstance(metrics, dict):
        return None
    out = {}
    for key, value in metrics.items():
        for suffix in QOR_SUFFIXES:
            # With *or* without the stage prefix. ORFS prefixes most
            # substeps' keys with the stage (`cts__timing__setup__ws`)
            # but not all of them: `5_3_fillcell.json` writes bare
            # `design__violations`, which an `endswith("__design__
            # violations")` test silently drops -- so that substep
            # compared no metrics at all and still reported `stable`.
            bare = suffix.lstrip("_")
            if key.endswith(suffix) or key == bare:
                out[bare] = value
                break
    return out


def differences(left, right):
    """Which QoR keys two samples disagree on, and by how much.

    Equality is exact. A metric that moved in the last decimal place is
    a divergence: this is a question about whether two runs computed the
    same thing, not about whether the difference matters.

    A key present in one sample and absent from the other is reported
    too -- a substep that stopped emitting a metric is itself a change.
    """
    left = left or {}
    right = right or {}
    out = {}
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            out[key] = (left.get(key), right.get(key))
    return out
