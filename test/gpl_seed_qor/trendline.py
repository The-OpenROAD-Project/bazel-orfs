"""The trendline the corpus is read against, and what is left over.

Phase A recovers, for 79 ORFS designs, the clock period and the setup
slack their CI accepts at global route. Those numbers are not comparable
as they stand -- a 1000 ps design and a 270 ps design, a 400-cell design
and a 200k-cell design -- so the question "is this design's QoR
surprising?" has no meaning until the systematic part is removed. That
is what this module does: fit what size and platform predict, subtract
it, and treat the residual as the prior.

## The response

`f = ws_gr / P`: setup worst slack at global route over the clock period
the same file implies. Dimensionless, so ps and ns designs sit on one
axis, and `min_period / P = 1 - f`. Negative f is a design that misses
its constraint.

## The censoring, which is the whole reason this is not ordinary least
squares

A design that closes writes `f >= 0` into its rules file and nothing
more (see rules_corpus). Dropping those rows would fit the trend on the
failures only and bias every residual; imputing them at zero would
pretend to know something the file does not say. Both are the standard
way to get this wrong.

So the fit is a **censored (Tobit) regression** by EM: censored rows
enter the M-step at their conditional expectation given that they are
censored, which is the mean of the truncated normal above the censoring
point,

    E[f | f >= 0, x] = xb + s * phi(a) / (1 - Phi(a)),  a = (0 - xb)/s

and the variance update carries the matching truncated second moment.
Uncensored rows enter as themselves. The iteration is the textbook one
and converges in tens of steps on data this size.

Implemented on numpy alone -- `math.erf` is enough for Phi -- so the
whole Phase A analysis runs without scipy, which keeps it reproducible
from a bare checkout.

## What a residual means

For an uncensored design the residual is `f - xb`, in units of its own
clock period: -0.05 means it lands 5% of a period worse than its size
and platform predict. For a censored design only a bound is available,
`f - xb >= -xb`, and it is reported as such rather than as a number.

The spread of those residuals is the prior the seed ensemble is measured
against: if a design's whole deviation from the trend is the size of
what changing a placement seed does, then the design is not the
interesting variable, the seed is.
"""

import math

import numpy as np

# EM stops when every coefficient and the scale move less than this
# between iterations. Far below the precision any conclusion is drawn
# at; it just has to be stable.
TOLERANCE = 1e-10

MAX_ITERATIONS = 500


def _phi(z):
    """Standard normal density."""
    return np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def _capital_phi(z):
    """Standard normal CDF, via math.erf so scipy is not a dependency."""
    return np.array([0.5 * (1.0 + math.erf(value / math.sqrt(2.0))) for value in
                     np.atleast_1d(z)]).reshape(np.shape(z))


def tobit_fit(design_matrix, response, censored, limit=0.0):
    """Right-censored linear regression by EM.

    Args:
        design_matrix: (n, k) covariates, including the intercept column.
        response: (n,) observed values; entries where `censored` is true
            are ignored and only the limit is used.
        censored: (n,) boolean, true where all that is known is
            `response >= limit`.
        limit: the censoring point.

    Returns:
        (beta, sigma, iterations).

    Raises:
        ValueError: when every row is censored, which carries no
            information about the slope at all.
    """
    design_matrix = np.asarray(design_matrix, dtype=float)
    response = np.asarray(response, dtype=float)
    censored = np.asarray(censored, dtype=bool)
    observed = ~censored
    if not observed.any():
        raise ValueError("every row is censored: nothing to fit")

    beta, *_ = np.linalg.lstsq(
        design_matrix[observed], response[observed], rcond=None
    )
    residual = response[observed] - design_matrix[observed] @ beta
    sigma = max(float(np.std(residual)), 1e-12)

    filled = response.copy()
    for iteration in range(1, MAX_ITERATIONS + 1):
        prediction = design_matrix @ beta
        alpha = (limit - prediction) / sigma
        tail = 1.0 - _capital_phi(alpha)
        # A censored row whose prediction is far below the limit has a
        # vanishing tail; clamping keeps the ratio finite and the step
        # in the right direction.
        tail = np.maximum(tail, 1e-12)
        lam = _phi(alpha) / tail
        filled[censored] = (prediction + sigma * lam)[censored]

        # Second moment of the truncated normal, for the scale update.
        second = sigma * sigma * (1.0 + alpha * lam - lam * lam)

        new_beta, *_ = np.linalg.lstsq(design_matrix, filled, rcond=None)
        new_residual = filled - design_matrix @ new_beta
        variance = float(
            (np.sum(new_residual**2) + np.sum(second[censored])) / len(filled)
        )
        new_sigma = max(math.sqrt(max(variance, 0.0)), 1e-12)

        step = max(
            float(np.max(np.abs(new_beta - beta))), abs(new_sigma - sigma)
        )
        beta, sigma = new_beta, new_sigma
        if step < TOLERANCE:
            break
    return beta, sigma, iteration


def build_design_matrix(rows, platforms):
    """Intercept, log10 size, and one column per platform after the first.

    Args:
        rows: dicts with `size` and `platform`.
        platforms: the platform order; the first is the reference level.

    Returns:
        (matrix, column_names).
    """
    names = ["intercept", "log10_instances"] + [
        "platform:%s" % platform for platform in platforms[1:]
    ]
    matrix = np.zeros((len(rows), len(names)))
    matrix[:, 0] = 1.0
    for index, row in enumerate(rows):
        matrix[index, 1] = math.log10(row["size"])
        if row["platform"] in platforms[1:]:
            matrix[index, 2 + platforms[1:].index(row["platform"])] = 1.0
    return matrix, names


def robust_sigma(values):
    """1.4826 * MAD: a spread one outlier cannot inflate.

    Args:
        values: the residuals.

    Returns:
        The estimate, or 0.0 for fewer than two values.
    """
    values = np.asarray(values, dtype=float)
    if values.size < 2:
        return 0.0
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def fit(rows, platforms=None):
    """Fit the trend and return every design's residual or bound.

    Args:
        rows: dicts with `platform`, `design`, `size`, `f` and
            `censored`.
        platforms: the platform order, defaulting to sorted order with
            the most populated first so the reference level is the one
            with the most support.

    Returns:
        A dict with the coefficients, the scale, per-design residuals
        (`residual` for observed rows, `residual_bound` for censored
        ones), and the robust spread of the observed residuals -- the
        prior a seed ensemble is compared against.
    """
    if platforms is None:
        counts = {}
        for row in rows:
            counts[row["platform"]] = counts.get(row["platform"], 0) + 1
        platforms = sorted(counts, key=lambda name: (-counts[name], name))

    matrix, names = build_design_matrix(rows, platforms)
    response = np.array([row["f"] if row["f"] is not None else 0.0 for row in rows])
    censored = np.array([bool(row["censored"]) for row in rows])
    beta, sigma, iterations = tobit_fit(matrix, response, censored)

    prediction = matrix @ beta
    designs = []
    observed_residuals = []
    for index, row in enumerate(rows):
        entry = {
            "platform": row["platform"],
            "design": row["design"],
            "size": row["size"],
            "predicted_f": float(prediction[index]),
            "censored": bool(censored[index]),
        }
        if censored[index]:
            # All that is known is f >= 0, so the residual is bounded
            # below by -prediction and unbounded above.
            entry["residual_bound"] = float(-prediction[index])
        else:
            entry["f"] = row["f"]
            entry["residual"] = float(row["f"] - prediction[index])
            observed_residuals.append(entry["residual"])
        designs.append(entry)

    return {
        "platforms": platforms,
        "coefficients": dict(zip(names, (float(value) for value in beta))),
        "sigma": float(sigma),
        "iterations": iterations,
        "n": len(rows),
        "n_censored": int(censored.sum()),
        "designs": designs,
        "residual_sigma_robust": robust_sigma(observed_residuals),
        "residual_range": (
            [min(observed_residuals), max(observed_residuals)]
            if observed_residuals
            else None
        ),
    }
