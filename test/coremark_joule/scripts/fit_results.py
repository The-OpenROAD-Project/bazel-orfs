"""The paper's fitted figures, from the pinned results.

4.6 reads the study through a log-log fit: a line through the three
cacheless cores, and what it predicts for the one core that was always
compliant. Those numbers were hand-computed and typed into the paper,
which is the one class of number in it that no artifact produced -- and
when the four points moved, three of the seven turned out to have been
slightly wrong.

So they are computed here, from results.json, by one stated method:
ordinary least squares on log10(CoreMark/Joule) against
log10(CoreMark/MHz).
"""

import argparse
import json
import math
import sys

CACHELESS = ("serv", "picorv32", "ibex")
COMPLIANT = "veer"


def fit(points):
    """OLS on log10(y) against log10(x); returns (slope, intercept, r2)."""
    xs = [math.log10(x) for x, _ in points]
    ys = [math.log10(y) for _, y in points]
    n = len(xs)
    if n < 2:
        raise SystemExit("a fit needs at least two points, got %d" % n)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise SystemExit("every point has the same x; the fit is undefined")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")
    return slope, intercept, r2


def figures(points):
    """Every fitted number 4.6 quotes, keyed as the paper names them."""
    by_core = {p["core"]: p for p in points}
    missing = [c for c in CACHELESS + (COMPLIANT,) if c not in by_core]
    if missing:
        raise SystemExit("results.json has no point for %s" % ", ".join(missing))

    def xy(core):
        p = by_core[core]
        return p["coremark_per_mhz"], p["coremark_per_joule"]

    three = [xy(c) for c in CACHELESS]
    slope, intercept, r2 = fit(three)
    vx, vy = xy(COMPLIANT)
    predicted = 10 ** (slope * math.log10(vx) + intercept)

    fp = {c: by_core[c]["frequency_mhz"] / (by_core[c]["power_w"] * 1000.0)
          for c in CACHELESS}
    powers = [by_core[c]["power_w"] for c in CACHELESS]
    slope4, _, r24 = fit(three + [(vx, vy)])
    return {
        "slope_cacheless": slope,
        "r2_cacheless": r2,
        "overpredicts_compliant_by": predicted / vy,
        "f_over_p_spread_cacheless": max(fp.values()) / min(fp.values()),
        "power_spread_cacheless": max(powers) / min(powers),
        "slope_all": slope4,
        "r2_all": r24,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    with open(args.results) as f:
        out = figures(json.load(f)["points"])
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
