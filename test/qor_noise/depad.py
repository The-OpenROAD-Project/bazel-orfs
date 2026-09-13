#!/usr/bin/env python3

"""Invert the padding `genRuleFile.py` applies, to recover measurements.

A `rules-base.json` entry is not a measurement. It is a measurement with
a margin added, rounded, and then written only if the update policy said
so. This module undoes the first two steps; `series.py` deals with the
third, which is the one that bites.

The padding modes are taken from `genRuleFile.py`'s `rules_dict`. Only
the modes this study relies on are implemented, and a metric whose mode
is not listed is refused rather than guessed at -- a metric silently
de-padded with the wrong rule would produce confident nonsense.

Two properties decide whether a metric is worth anything here:

  * **invertibility.** `mode: padding` is `rule = m * (1 + p/100)`, which
    inverts exactly. `mode: metric` computes the rule from a *different*
    metric entirely -- `cts__design__instance__count__setup_buffer` is
    10% of the placeopt stdcell count -- so it tells you nothing about
    the metric it is named after, and is excluded.
  * **resolution.** `round_value: True` stores `int(round(...))`, which
    for an area of 10^5 is seven significant digits. `round_value: False`
    stores `float(f"{v:.3g}")` -- three significant digits, a quantisation
    of up to 0.5%, which is the same order as the effects being hunted.
    Three-digit metrics are usable but their resolution is stated.

The timing metrics deserve their own warning, in TIMING_IS_CENSORED.
"""

# metric -> (mode, padding, round_value)
PADDING = {
    "synth__design__instance__area__stdcell": ("padding", 15, False),
    "placeopt__design__instance__area": ("padding", 15, True),
    "placeopt__design__instance__count__stdcell": ("padding", 15, True),
    "detailedroute__route__wirelength": ("padding", 15, True),
    "detailedroute__antenna__violating__nets": ("padding", 30, True),
    "finish__design__instance__area": ("padding", 15, True),
    # Exact: the rule is the measurement, no margin at all.
    "constraints__clocks__count": ("direct", 0, True),
    "detailedplace__design__violations": ("direct", 0, True),
    "detailedroute__route__drc_errors": ("direct", 0, True),
    # Timing. `period_padding` with negative_slack = min(m, 0):
    #     rule = negative_slack - period * p / 100
    # so the measurement is recoverable ONLY when it was negative.
    "cts__timing__setup__ws": ("period_padding", 5, False),
    "cts__timing__setup__tns": ("period_padding", 20, False),
    "cts__timing__hold__ws": ("period_padding", 5, False),
    "cts__timing__hold__tns": ("period_padding", 20, False),
    "globalroute__timing__setup__ws": ("period_padding", 5, False),
    "globalroute__timing__setup__tns": ("period_padding", 20, False),
    "globalroute__timing__hold__ws": ("period_padding", 5, False),
    "globalroute__timing__hold__tns": ("period_padding", 20, False),
    "finish__timing__setup__ws": ("period_padding", 5, False),
    "finish__timing__setup__tns": ("period_padding", 20, False),
    "finish__timing__hold__ws": ("period_padding", 5, False),
    "finish__timing__hold__tns": ("period_padding", 20, False),
}

# Computed from a different metric; says nothing about its own name.
NOT_ABOUT_ITSELF = {
    "cts__design__instance__count__setup_buffer",
    "cts__design__instance__count__hold_buffer",
    "globalroute__antenna_diodes_count",
    "detailedroute__antenna_diodes_count",
}

TIMING_IS_CENSORED = """\
For a `period_padding` metric the stored rule is

    rule = min(measured, 0) - period * padding / 100

so whenever the design MEETS its constraint the rule collapses to the
constant -period*padding/100, identical for every passing run. The
threshold then carries exactly one bit -- "it passed" -- and no amount of
history will tell you whether slack was 1 ps or 1 ns. A design that
closes is invisible on the timing axis, and a timing rule cannot detect
a regression until closure has already been lost."""

# The metrics that are both exactly invertible and stored at full integer
# precision. Everything quantitative in this study leans on these.
HIGH_RESOLUTION = [
    "placeopt__design__instance__area",
    "placeopt__design__instance__count__stdcell",
    "detailedroute__route__wirelength",
    "finish__design__instance__area",
]

# Smaller is better for every metric this study de-pads.
LOWER_IS_BETTER = set(PADDING) - {
    "cts__timing__setup__ws",
    "cts__timing__setup__tns",
    "cts__timing__hold__ws",
    "cts__timing__hold__tns",
    "globalroute__timing__setup__ws",
    "globalroute__timing__setup__tns",
    "globalroute__timing__hold__ws",
    "globalroute__timing__hold__tns",
    "finish__timing__setup__ws",
    "finish__timing__setup__tns",
    "finish__timing__hold__ws",
    "finish__timing__hold__tns",
    "constraints__clocks__count",
}


class NotDepaddable(Exception):
    """Raised for a metric whose rule cannot be turned back into a value."""


def resolution(metric):
    """Fractional quantisation of the stored rule, as a fraction of value.

    `round_value: True` stores an integer, so the quantisation is one
    unit -- negligible for the quantities here and reported as 0.0 to
    mean "below anything we care about". `round_value: False` keeps three
    significant digits, whose worst-case relative step is 1/100.
    """
    if metric not in PADDING:
        raise NotDepaddable(metric)
    _mode, _pad, round_value = PADDING[metric]
    return 0.0 if round_value else 0.01


def depad(metric, rule_value, period=None):
    """Recover the measured value that produced `rule_value`.

    Returns None when the rule is real but carries no measurement, which
    happens for a passing timing metric (see TIMING_IS_CENSORED).
    """
    if metric in NOT_ABOUT_ITSELF:
        raise NotDepaddable(f"{metric} is computed from another metric")
    if metric not in PADDING:
        raise NotDepaddable(metric)
    mode, pad, _round_value = PADDING[metric]
    if rule_value is None:
        return None

    if mode == "direct":
        return float(rule_value)

    if mode == "padding":
        return float(rule_value) / (1.0 + pad / 100.0)

    if mode == "period_padding":
        if period is None:
            raise NotDepaddable(f"{metric} needs the clock period")
        floor = -period * pad / 100.0
        # The rule is exactly the floor (to within storage rounding) when
        # the design met its constraint: no measurement is recoverable.
        if rule_value >= floor - abs(floor) * 1e-6:
            return None
        return float(rule_value) + period * pad / 100.0

    raise NotDepaddable(f"{metric} has unhandled mode {mode}")
