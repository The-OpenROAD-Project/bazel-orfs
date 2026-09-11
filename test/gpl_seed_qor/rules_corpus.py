"""What ORFS's own rules files already know, and how to read it back out.

Every ORFS design ships a `rules-base.json`: the metric bounds its CI
accepts. They look like thresholds rather than measurements, and that is
how they are used -- but for the timing metrics the padding is a closed
form with one unknown, so the measurement and the clock period can both
be recovered exactly. That turns 79 files nobody has to run into a prior:
what QoR a design of a given size on a given platform is currently
accepted at.

## The inversion

`flow/util/genRuleFile.py` builds the timing bounds in `period_padding`
mode:

    rule = min(m, 0) - max(min(m,0) * p/100, P * p/100)

with `m` the measured metric, `P` the first clock's period, and `p` the
padding percent -- 5 for every `*__ws`, 20 for every `*__tns`. The first
argument of the `max` is <= 0 and the second is > 0 for any positive
period, so the `max` always takes the second and the whole thing
collapses to

    rule = min(m, 0) - (p/100) * P                                  (1)

Two facts follow, and the whole module is built on them.

**The period is identified.** Rearranging (1), `(p/100)*P = min(m,0) -
rule <= -rule`, so every period_padding metric is an *upper bound*

    P <= -rule * 100/p                                              (2)

with equality exactly when that metric was non-negative. ORFS writes
twelve of them -- cts/globalroute/finish x setup/hold x ws/tns -- so the
period is the minimum of twelve bounds, exact as soon as any one of the
twelve closed. Hold usually does. When several bounds agree the estimate
is corroborated rather than merely assumed, which is what
`period_witnesses` counts.

**The measurement comes back** wherever the metric was negative:

    m = rule + (p/100) * P                                          (3)

and where it was not, the file says `m >= 0` -- a censored observation,
not a missing one. `asap7/aes` reads back a 380 ps clock and -8.8 ps of
setup WNS at global route, and its `constraint.sdc` says `set clk_period
380`. That agreement, checked per design, is what keeps this honest.

## What it cannot do

The files were regenerated at different times by different tool versions,
so this is a snapshot of what is accepted, not a controlled experiment.
`genRuleFile.py` uses the *first* clock when a design declares several,
so a multi-clock design's period means less than it looks like.  Values
are rounded to three significant figures, which puts a ~0.05% floor on
anything recovered through (3). And a file older than the current padding
policy -- or written when `constraints__clocks__details` was absent, in
which case genRuleFile used `period = 0` and (1) degenerates to `rule =
min(m,0)` -- inverts to a period that is not a period. Those designs are
reported with a `note` and excluded by the caller; `asap7/coralnpu`,
whose hold bound implies a 10 ps clock, is the reason this is a named
case rather than an assumption.

Units are whatever the design's SDC uses -- ps on asap7, ns on nangate45
-- which is why every response variable downstream is the dimensionless
`ws/P` rather than a time.
"""

import argparse
import json
import math
import os
import re
import sys

# The twelve period_padding metrics genRuleFile.py writes, and the
# padding percent each is written with. Anything not in here is padded
# some other way (or not at all) and is not invertible by (1).
PERIOD_PADDING = {
    "cts__timing__setup__ws": 5,
    "cts__timing__setup__tns": 20,
    "cts__timing__hold__ws": 5,
    "cts__timing__hold__tns": 20,
    "globalroute__timing__setup__ws": 5,
    "globalroute__timing__setup__tns": 20,
    "globalroute__timing__hold__ws": 5,
    "globalroute__timing__hold__tns": 20,
    "finish__timing__setup__ws": 5,
    "finish__timing__setup__tns": 20,
    "finish__timing__hold__ws": 5,
    "finish__timing__hold__tns": 20,
}

# Covariates carried alongside, for the trendline. These are padded too
# (15%), but only their *order* is used, and a constant factor does not
# change a log-scale fit's residuals.
COVARIATES = [
    "synth__design__instance__area__stdcell",
    "placeopt__design__instance__count__stdcell",
    "placeopt__design__instance__area",
    "finish__design__instance__area",
    "detailedroute__route__wirelength",
]

# Two bounds count as agreeing when they are within this relative
# distance. Three significant figures on the rule value is a 5e-4
# relative quantisation, and two rules quantised independently can
# disagree by twice that.
BOUND_TOLERANCE = 2e-3

# Below this, a recovered period is not a clock. The tightest clock in
# the corpus is on the order of a hundred time units; a bound that
# implies a period two orders below its siblings is a file that predates
# the current padding policy, not a fast design.
MIN_PLAUSIBLE_PERIOD = 1e-9


def period_bound(rule_value, padding_pct):
    """The upper bound on the clock period implied by one rule -- (2).

    Args:
        rule_value: the `value` field of a period_padding metric.
        padding_pct: its padding, from PERIOD_PADDING.

    Returns:
        The bound, or None when the rule carries no bound (a
        non-negative rule value, which (1) cannot produce for a positive
        period, so it says the file was written with period = 0).
    """
    if rule_value is None or rule_value >= 0:
        return None
    return -rule_value * 100.0 / padding_pct


def recover_period(rules):
    """Recover the clock period from the twelve padded timing bounds.

    Args:
        rules: the parsed rules-base.json dict.

    Returns:
        (period, witnesses, bounds): the minimum bound, how many metrics
        attain it within BOUND_TOLERANCE (1 means uncorroborated), and
        the per-metric bounds. period is None when no metric carries one.
    """
    bounds = {}
    for metric, padding in PERIOD_PADDING.items():
        entry = rules.get(metric)
        if entry is None:
            continue
        bound = period_bound(entry.get("value"), padding)
        if bound is not None:
            bounds[metric] = bound
    if not bounds:
        return None, 0, bounds
    period = min(bounds.values())
    witnesses = sum(
        1 for b in bounds.values() if abs(b - period) <= BOUND_TOLERANCE * period
    )
    return period, witnesses, bounds


def rule_resolution(rule_value):
    """Half the quantum ORFS's three-significant-figure rounding leaves.

    A rule written as -19.0 could have been anything in [-19.05, -18.95)
    before rounding, so nothing recovered through it is meaningful below
    0.05. This is the study's resolution floor, and it is derived from
    the stored value rather than assumed, because the quantum depends on
    the value's magnitude: a -19.0 bound resolves to 0.05, a -1737 bound
    only to 5.

    Args:
        rule_value: the stored bound.

    Returns:
        The resolution, or 0.0 for a zero bound (which carries no
        magnitude to derive one from).
    """
    if not rule_value:
        return 0.0
    magnitude = math.floor(math.log10(abs(rule_value)))
    return 10.0 ** (magnitude - 2) / 2.0


def recover_measurement(rule_value, padding_pct, period):
    """Undo the padding -- (3).

    Args:
        rule_value: the `value` field of a period_padding metric.
        padding_pct: its padding, from PERIOD_PADDING.
        period: the recovered clock period.

    Returns:
        (value, censored). `censored` means the metric was non-negative
        when the rule was written, so the file bounds it (`>= 0`) rather
        than recording it, and `value` is None. A violation smaller than
        the rounding resolution is indistinguishable from zero and reads
        as censored: that is a limit of the data, and it is where this
        errs rather than inventing a slack the file cannot carry.
    """
    if rule_value is None or period is None:
        return None, False
    value = rule_value + padding_pct / 100.0 * period
    if value >= -rule_resolution(rule_value):
        return None, True
    return value, False


# `set clk_period 380`, the shape almost every ORFS SDC uses, and a
# literal `-period 380` for the ones that inline it. Anything else --
# an $::env() indirection, a period computed in Tcl -- is left
# unresolved rather than guessed at.
_SET_CLK_PERIOD = re.compile(r"^\s*set\s+clk_period\s+([0-9.eE+-]+)\s*$", re.M)
LITERAL_PERIOD = re.compile(r"create_clock[^\n]*?-period\s+([0-9.]+)")
# Kept under the old private name too: this module's own code reads it.
_LITERAL_PERIOD = LITERAL_PERIOD


def clock_from_sdc(design_dir):
    """The design's clock period as its SDC states it, for cross-checking.

    Args:
        design_dir: the design's directory in an ORFS source tree.

    Returns:
        (period, source_file) or (None, reason).
    """
    if not os.path.isdir(design_dir):
        return None, "no design directory"
    sdcs = sorted(f for f in os.listdir(design_dir) if f.endswith(".sdc"))
    if not sdcs:
        return None, "no sdc"
    for name in sdcs:
        path = os.path.join(design_dir, name)
        with open(path) as handle:
            text = handle.read()
        match = _SET_CLK_PERIOD.search(text) or _LITERAL_PERIOD.search(text)
        if match:
            return float(match.group(1)), name
    return None, "no literal period in %s" % ",".join(sdcs)


def parse_design(platform, design, rules_path, design_dir=None):
    """One corpus row: everything recoverable about one design.

    Args:
        platform: the PDK directory name.
        design: the design directory name.
        rules_path: path to its rules-base.json.
        design_dir: its directory, for the SDC cross-check. Defaults to
            the directory holding rules_path.

    Returns:
        A dict with the recovered period, the recovered metrics, the
        covariates, and a `notes` list naming everything that could not
        be established.
    """
    with open(rules_path) as handle:
        rules = json.load(handle)

    if design_dir is None:
        design_dir = os.path.dirname(rules_path)

    period, witnesses, bounds = recover_period(rules)
    notes = []

    sdc_period, sdc_source = clock_from_sdc(design_dir)
    if period is None:
        notes.append("no period bound: no negative timing rule in the file")
    elif period < MIN_PLAUSIBLE_PERIOD:
        notes.append("recovered period %g is not a clock" % period)
    if witnesses == 1:
        notes.append("period from a single bound, uncorroborated")
    if sdc_period is None:
        notes.append("sdc: %s" % sdc_source)
    elif period is not None and abs(sdc_period - period) > BOUND_TOLERANCE * sdc_period:
        notes.append(
            "sdc says %g, rules imply %g" % (sdc_period, period),
        )

    clocks = rules.get("constraints__clocks__count", {}).get("value")
    if isinstance(clocks, (int, float)) and clocks > 1:
        notes.append("%d clocks; genRuleFile pads with the first" % clocks)

    metrics = {}
    for metric, padding in PERIOD_PADDING.items():
        entry = rules.get(metric)
        if entry is None:
            continue
        value, censored = recover_measurement(entry.get("value"), padding, period)
        metrics[metric] = {
            "rule": entry.get("value"),
            "value": value,
            "censored": censored,
        }

    row = {
        "platform": platform,
        "design": design,
        "period": period,
        "period_witnesses": witnesses,
        "period_from_sdc": sdc_period,
        "sdc_source": sdc_source if sdc_period is not None else None,
        "clocks": clocks,
        "metrics": metrics,
        "covariates": {
            name: rules[name]["value"] for name in COVARIATES if name in rules
        },
        "notes": notes,
    }
    return row


def build_corpus(orfs_root):
    """Every design in an ORFS source tree that ships a rules-base.json.

    Args:
        orfs_root: a directory holding `flow/designs/<platform>/<design>`.

    Returns:
        The rows, sorted by platform then design.
    """
    designs_dir = os.path.join(orfs_root, "flow", "designs")
    rows = []
    for dirpath, _, filenames in os.walk(designs_dir):
        if "rules-base.json" not in filenames:
            continue
        relative = os.path.relpath(dirpath, designs_dir).split(os.sep)
        if len(relative) < 2:
            continue
        platform, design = relative[0], "/".join(relative[1:])
        rows.append(
            parse_design(
                platform,
                design,
                os.path.join(dirpath, "rules-base.json"),
                dirpath,
            )
        )
    return sorted(rows, key=lambda row: (row["platform"], row["design"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--orfs-root",
        required=True,
        help="ORFS source tree holding flow/designs (see the reproducing "
        "section: `git archive <pinned commit>` of the rules and sdc files "
        "is enough, the tree need not be complete)",
    )
    parser.add_argument(
        "--orfs-commit",
        default="",
        help="recorded in the snapshot, so a row can never be read against "
        "the wrong ORFS",
    )
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args(argv)

    rows = build_corpus(args.orfs_root)
    if not rows:
        sys.exit("no rules-base.json under %s/flow/designs" % args.orfs_root)

    snapshot = {
        "orfs_commit": args.orfs_commit,
        "designs": rows,
    }
    with open(args.out_json, "w") as handle:
        json.dump(snapshot, handle, indent=2, sort_keys=True)
        handle.write("\n")

    flagged = sum(1 for row in rows if row["notes"])
    print("%d designs, %d with notes -> %s" % (len(rows), flagged, args.out_json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
