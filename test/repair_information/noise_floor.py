"""The two floors an effect in this study has to clear, and the reason
they are different numbers.

**The tolerance bar** is what CI would even notice. ORFS's
`genRuleFile.py` builds `rules-base.json` by padding a measured run:
setup worst slack in `period_padding` mode at 5% (hold at 20%), area and
instance counts at 15%, and so on. So `rules-base.json` is *not* a noise
measurement -- it records a padded threshold, and on the asap7 designs it
does not even record the unpadded number next to it. Read as a floor it
says only: a change smaller than 5% of the clock period will never fail a
rule, whatever it does to the design.

**The measured floor** is what this machine can resolve. It comes from
repeats of the same arm with only the placement seed varied, as 2 sigma
of the sample, and the difference resolvable at k runs per arm is
`2 sigma * sqrt(2/k)`. This is the bar a *result* has to clear. The
pre-route-pessimism study measured 2 sigma = 47.5 ps for `min_period` at
global route on a contended asap7 design -- 3.6x the spread of the
placement estimate it is supposed to be correcting -- so on this flow the
measured floor can be much larger than the tolerance bar, and an effect
can be invisible to CI and still real, or visible to CI and still noise.

Reporting one without the other is how a study says "no effect" when it
means "did not resolve", or "improves QoR" when it means "moved less than
the seed does".
"""

import json
import math
from pathlib import Path

# genRuleFile.py's padding for the metrics this study reads. Setup slack
# is padded as a percentage of the clock period, not of the slack, which
# is the same convention check_pareto.py argues for on the period axis.
PERIOD_PADDING_PERCENT = 5.0
AREA_PADDING_PERCENT = 15.0


def tolerance_bar_ps(clock_period_ps, padding_percent=PERIOD_PADDING_PERCENT):
    """The smallest timing change CI could notice, in the clock's units."""
    return clock_period_ps * padding_percent / 100.0


def two_sigma(samples):
    """Spread as 2 sigma. A single sample has zero spread, which is
    honest: one run says nothing about how much the flow moves on its
    own, and pretending otherwise is the error this study is about."""
    n = len(samples)
    if n < 2:
        return 0.0
    mean = sum(samples) / n
    var = sum((s - mean) ** 2 for s in samples) / (n - 1)
    return 2.0 * math.sqrt(var)


def resolvable(samples_per_arm, sigma2):
    """The difference between two arms that k runs each can resolve.

    Below this the verdict is "did not resolve" -- never "no effect".
    """
    if samples_per_arm < 1:
        raise ValueError("an arm with no runs resolves nothing")
    return sigma2 * math.sqrt(2.0 / samples_per_arm)


def read_rule(path, metric):
    """One threshold out of a rules-base.json, or None if absent.

    Absent is a real answer: not every design carries every rule, and a
    missing rule must not silently become a zero bar.
    """
    rules = json.loads(Path(path).read_text())
    entry = rules.get(metric)
    if not isinstance(entry, dict) or "value" not in entry:
        return None
    return float(entry["value"])


def floors(design, clock_period_ps, samples=(), rules_path=None):
    """Both floors for one design, side by side.

    `samples` are repeated min_period readings of the same arm, differing
    only in placement seed.
    """
    sigma2 = two_sigma(list(samples))
    out = {
        "design": design,
        "clock_period_ps": clock_period_ps,
        "tolerance_bar_ps": tolerance_bar_ps(clock_period_ps),
        "repeats": len(samples),
        "two_sigma_ps": sigma2,
        "resolvable_ps": resolvable(len(samples), sigma2) if samples else None,
        "measured": bool(samples),
    }
    if rules_path is not None:
        out["rule_setup_ws"] = read_rule(rules_path, "finish__timing__setup__ws")
    return out


def verdict(delta_ps, floor):
    """What may honestly be said about a measured difference.

    The order matters: a difference inside the resolution is not a
    result at all, so it is never described in terms of the tolerance
    bar it also happens to be inside.
    """
    resolution = floor.get("resolvable_ps")
    if resolution is None:
        return "not measured: no repeats, so the flow's own spread is unknown"
    if abs(delta_ps) <= resolution:
        return "did not resolve"
    if abs(delta_ps) <= floor["tolerance_bar_ps"]:
        return "resolved, below the CI tolerance bar"
    return "resolved, above the CI tolerance bar"
