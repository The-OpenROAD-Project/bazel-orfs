"""The arithmetic that decides whether an arm did anything.

Nine arms against a baseline, on a dozen designs, is 96 comparisons. At
a 2-sigma per-comparison threshold roughly five of them come back
"resolved" when nothing is happening at all, so a table of per-design
verdicts cannot carry a conclusion on its own -- it will always contain
a few confident-looking rows, and the reader has no way to tell which.

This module implements the two-part rule the study uses instead:

1. **Per design**, an arm is *resolved* when the difference of the
   means exceeds `2 * SE(difference)`. Inside that band the verdict is
   **did not resolve**, which is a different statement from "no effect"
   and is never rendered as agreement.

2. **Across designs**, an arm is a *finding* only when at least `k` of
   `D` designs resolve **in the same direction**. bazel-orfs PR #981
   measured that real tool changes are direction-coherent across the
   fleet (median concordance 98.4%, and 12 of 12 for pure OpenROAD
   bumps) while draws are not, which is what licenses using direction
   as the test statistic rather than a pooled p-value.

`required_concordance()` picks `k` from `D` so the family-wise rate over
every arm stays near 1%, and `family_error()` reports what that rate
actually is, so the threshold is a number in the report rather than a
convention. With D = 12 and 8 arms, requiring 4 of 12 gives ~0.4%.
"""

import math


def mean(values):
    """The arithmetic mean.

    Args:
        values: a non-empty sequence of numbers.

    Returns:
        The mean.

    Raises:
        ValueError: on an empty sequence, rather than returning a zero
            that would read as a measurement.
    """
    if not values:
        raise ValueError("mean of no samples")
    return sum(values) / len(values)


def stdev(values):
    """The sample standard deviation (n-1).

    Args:
        values: a sequence of numbers.

    Returns:
        The deviation, or 0.0 for fewer than two samples -- which is
        honest: one run has no spread, and the resolution it implies is
        correctly infinite rather than zero.
    """
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def spread(values):
    """Mean and 2-sigma of an ensemble.

    Args:
        values: the ensemble.

    Returns:
        {n, mean, sd, two_sigma, min, max}.
    """
    return {
        "n": len(values),
        "mean": mean(values),
        "sd": stdev(values),
        "two_sigma": 2 * stdev(values),
        "min": min(values),
        "max": max(values),
    }


def resolution(baseline, arm):
    """The smallest difference these two ensembles can distinguish.

    Twice the standard error of the difference of the means, so it is
    the same 2-sigma convention the per-arm spreads are quoted in.

    Args:
        baseline: the baseline ensemble's values.
        arm: the arm's values.

    Returns:
        The resolution in the ensembles' own units. Infinite when either
        arm has fewer than two samples, because a single run cannot
        bound anything and reporting 0.0 there would turn every
        one-sample arm into a resolved result.
    """
    if len(baseline) < 2 or len(arm) < 2:
        return math.inf
    var_b = stdev(baseline) ** 2 / len(baseline)
    var_a = stdev(arm) ** 2 / len(arm)
    return 2 * math.sqrt(var_b + var_a)


def compare(baseline, arm):
    """One design, one arm, against the baseline.

    Args:
        baseline: the baseline ensemble's values.
        arm: the arm's values.

    Returns:
        {delta, resolution, verdict, direction, baseline, arm} where
        `delta` is arm minus baseline, `verdict` is "resolved" or "did
        not resolve", and `direction` is -1, 0 or +1 and is 0 unless the
        comparison resolved -- an unresolved sign is not evidence and
        must not reach the concordance count.
    """
    delta = mean(arm) - mean(baseline)
    limit = resolution(baseline, arm)
    resolved = abs(delta) > limit
    return {
        "delta": delta,
        "resolution": limit,
        "verdict": "resolved" if resolved else "did not resolve",
        "direction": (0 if not resolved else (1 if delta > 0 else -1)),
        "baseline": spread(baseline),
        "arm": spread(arm),
    }


def binomial_tail(n, k, p):
    """P(at least k successes in n trials), each with probability p.

    Args:
        n: trials.
        k: successes.
        p: per-trial probability.

    Returns:
        The upper tail. k <= 0 is 1.0; k > n is 0.0.
    """
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    total = 0.0
    for i in range(k, n + 1):
        total += math.comb(n, i) * (p**i) * ((1 - p) ** (n - i))
    return total


# P(a single design resolves in one specified direction) under the null.
# A 2-sigma two-sided band leaves ~5% outside it, half of which is in
# each direction.
NULL_PER_DESIGN = 0.025


def family_error(designs, required, arms, per_design=NULL_PER_DESIGN):
    """The chance this rule declares at least one arm real by accident.

    Args:
        designs: how many designs each arm was run on.
        required: how many must resolve in the same direction.
        arms: how many arms are being tested against the baseline.
        per_design: the null probability of one design resolving in one
            specified direction.

    Returns:
        The family-wise false-positive rate, bounded above by the union
        bound over arms and directions. Quoted in the report rather than
        assumed, so a reader can see what the threshold bought.
    """
    one_arm = 2 * binomial_tail(designs, required, per_design)
    return min(1.0, arms * one_arm)


def required_concordance(designs, arms, target=0.01, per_design=NULL_PER_DESIGN):
    """The smallest `k` whose family-wise rate is under `target`.

    Args:
        designs: how many designs each arm was run on.
        arms: how many arms are tested against the baseline.
        target: the family-wise rate to stay under.
        per_design: as family_error().

    Returns:
        `k`, in [1, designs]. Returns `designs` when even unanimity
        cannot reach the target, which is the honest answer for a
        campaign with too few designs to conclude anything.
    """
    for k in range(1, designs + 1):
        if family_error(designs, k, arms, per_design) <= target:
            return k
    return designs


def concordance(comparisons):
    """Pool one arm's per-design comparisons into a verdict.

    Args:
        comparisons: the compare() dicts for this arm, one per design.

    Returns:
        {designs, resolved, up, down, direction, agree} where `agree` is
        the larger of `up` and `down` -- the count the concordance rule
        is applied to -- and `direction` is the sign that count belongs
        to, or 0 on a tie.
    """
    up = sum(1 for row in comparisons if row["direction"] > 0)
    down = sum(1 for row in comparisons if row["direction"] < 0)
    direction = 0
    if up > down:
        direction = 1
    elif down > up:
        direction = -1
    return {
        "designs": len(comparisons),
        "resolved": up + down,
        "up": up,
        "down": down,
        "agree": max(up, down),
        "direction": direction,
    }


def verdict(comparisons, arms, target=0.01):
    """The arm's finding, or the reason there isn't one.

    Args:
        comparisons: the compare() dicts for this arm, one per design.
        arms: how many arms share the family-wise budget.
        target: the family-wise rate to stay under.

    Returns:
        {label, required, family_error, ...concordance fields}. `label`
        is one of:

        * `"better"` / `"worse"`  -- enough designs resolved the same
          way; sign convention is the caller's, since a lower HPWL is
          better and a lower iteration count is cheaper but a lower
          `min_period` is also better, so all three share it.
        * `"did not resolve"`     -- nothing resolved anywhere.
        * `"inconsistent"`        -- designs resolved in both directions
          often enough that neither side meets the rule. Kept distinct
          because it is evidence of a real but design-dependent effect,
          which is not the same as evidence of nothing.
        * `"underpowered"`        -- too few designs for any threshold to
          reach `target` across `arms`. Overrides every other label: a
          campaign this small cannot produce a finding, and must not be
          allowed to print one.
    """
    pooled = concordance(comparisons)
    required = required_concordance(len(comparisons), arms, target)
    error = family_error(len(comparisons), required, arms)
    label = "did not resolve"
    if error > target:
        # Too few designs for any concordance threshold to buy the
        # target rate: even unanimity would be inside what chance
        # produces across this many arms. Saying "better" here would be
        # the study's own worst failure mode -- a confident word on top
        # of a number that cannot support it -- so the label says what
        # is actually wrong instead.
        label = "underpowered"
    elif pooled["agree"] >= required and pooled["direction"] != 0:
        label = "better" if pooled["direction"] < 0 else "worse"
    elif pooled["resolved"] >= required:
        label = "inconsistent"
    out = dict(pooled)
    out.update(
        {
            "label": label,
            "required": required,
            "family_error": error,
            "underpowered": error > target,
        }
    )
    return out
