#!/usr/bin/env python3
"""Give TimesFM the same task, scored the same way.

The question this answers is narrow and worth stating exactly: does a
time-series foundation model, handed the same prefix as `naive` and
`parametric`, forecast an ORFS grind well enough to change a decision?

Two things have to be got right for the comparison to be fair:

*Resampling.* These series are emitted per iteration, not per second --
OpenROAD prints every 10 iterations and iterations are not equal length.
A fixed-horizon forecaster expects a uniform grid, so the metric is
resampled onto one before TimesFM sees it. Feeding it the raw
iteration-indexed series would be handing it a distorted time axis and
then blaming it for the distortion.

*The same question.* TimesFM forecasts values; the decision needs a
crossing time. So the forecast is rolled forward and the first crossing
of the target is read off, exactly as the parametric fit does. No
crossing inside the horizon is read as "this will not converge" -- the
same rule the other forecasters are held to.
"""

import argparse
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest
import forecast

# One sample per second: coarse enough that a 300s grind fits in a few
# hundred points, fine enough to locate a crossing usefully.
GRID_S = 1.0
# Smallest metric value the log transform will represent.
TINY = 1e-6
# How far past the context to look for a crossing, in grid steps.
HORIZON = 256


def resample(points, grid_s=GRID_S):
    """Metric on a uniform time grid, by last-value carry-forward."""
    pts = [p for p in points if p.t is not None and p.metric is not None]
    if len(pts) < 2:
        return None, None
    t0 = pts[0].t
    span = pts[-1].t - t0
    if span <= 0:
        return None, None
    n = int(span / grid_s) + 1
    out = []
    j = 0
    for i in range(n):
        t = i * grid_s
        while j + 1 < len(pts) and (pts[j + 1].t - t0) <= t:
            j += 1
        out.append(pts[j].metric)
    return out, t0


def load_model():
    import timesfm

    # The 2.5/3.0 torch entry point. Kept in one place so an API change
    # is a one-line fix rather than a hunt.
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        "google/timesfm-2.5-200m-pytorch"
    )
    model.compile(
        timesfm.ForecastConfig(
            max_context=1024,
            max_horizon=HORIZON,
            normalize_inputs=True,
        )
    )
    return model


def eta_from_forecast(values, floor, grid_s=GRID_S):
    """First forecast step where the metric falls to the floor.

    Values arrive as log10 of the metric, because that is the space
    these curves are shaped in: endpoint TNS falls from 12639 to 0.2
    over one run, four orders of magnitude. Asked to forecast that in
    linear space with input normalization, TimesFM declined on every
    run at the 30s checkpoint -- it never predicted a value near zero,
    which says more about the transform it was given than about the
    model. The log-space series is the same one `parametric` fits.
    """
    log_floor = math.log10(max(floor, TINY))
    for i, v in enumerate(values):
        if v <= log_floor:
            return (i + 1) * grid_s
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus")
    ap.add_argument("--checkpoints", default="5,15,30")
    args = ap.parse_args(argv)

    series = [s for s in backtest.load(args.corpus) if backtest.usable(s)]
    model = load_model()

    print("{:12s} {:>6s} {:>5s} {:>9s} {:>11s}".format(
        "forecaster", "at", "n", "declined", "median APE"))
    print("-" * 48)

    for at in [float(x) for x in args.checkpoints.split(",")]:
        apes = {"timesfm": [], "naive": []}
        declined = {"timesfm": 0, "naive": 0}
        n = 0
        for s in series:
            if not s.converged:
                continue
            k = backtest.checkpoint_index(s, at)
            if k is None:
                continue
            grid, _ = resample(s.points[: k + 1])
            if not grid or len(grid) < 8:
                continue
            n += 1
            truth = forecast.truth_remaining(s, k)

            log_grid = [math.log10(max(v - s.target, TINY)) for v in grid]
            # Same stopping rule the other forecasters get: one more
            # reporting step counts as finished.
            steps = [
                abs(grid[i] - grid[i + 1])
                for i in range(len(grid) - 1)
                if grid[i] != grid[i + 1]
            ]
            floor = statistics.median(steps) if steps else TINY

            point_forecast, _ = model.forecast(
                horizon=HORIZON, inputs=[log_grid]
            )
            pred = eta_from_forecast(list(point_forecast[0]), floor)
            if pred is None:
                declined["timesfm"] += 1
            elif truth and truth > 0:
                apes["timesfm"].append(abs(pred - truth) / truth)

            nv = forecast.naive(s.points[: k + 1], s.target)
            if nv is None:
                declined["naive"] += 1
            elif truth and truth > 0:
                apes["naive"].append(abs(nv - truth) / truth)

        for name in ("timesfm", "naive"):
            med = (
                "{:.0%}".format(statistics.median(apes[name]))
                if apes[name]
                else "-"
            )
            print("{:12s} {:>5.0f}s {:>5d} {:>9d} {:>11s}".format(
                name, at, n, declined[name], med))
    return 0


if __name__ == "__main__":
    sys.exit(main())
