#!/usr/bin/env python3
"""Plot CoreMark/Joule against CoreMark/MHz from the pinned results.

Reads results.json and nothing else, so iterating on the presentation
never re-runs a flow.

Both axes are logarithmic because the interesting range spans decades:
the cores worth comparing run from a bit-serial design at hundredths of a
CoreMark/MHz to out-of-order designs above ten, and energy efficiency
spreads at least as far.

The plot is the study's whole point. Performance per clock and energy per
unit work are not the same axis -- a design can be slow and wasteful at
once -- and the shape of the relationship between them is what a
screening study can say something about.
"""

import argparse
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot(document, out_path):
    points = document["points"]
    if not points:
        raise ValueError("no points to plot")

    fig, ax = plt.subplots(figsize=(7.5, 5.5))

    xs = [p["coremark_per_mhz"] for p in points]
    ys = [p["coremark_per_joule"] for p in points]

    ax.scatter(xs, ys, s=70, zorder=3)
    for p in points:
        ax.annotate(
            "{} ({})".format(p["core"], p["isa"]),
            (p["coremark_per_mhz"], p["coremark_per_joule"]),
            textcoords="offset points",
            xytext=(9, -4),
            fontsize=9,
        )

    ax.set_xscale("log")
    ax.set_yscale("log")

    # Decades-wide data in matplotlib's default log formatting produces
    # minor-tick labels that collide into each other. Plain numbers on
    # the decades, nothing on the minors, and a margin so a point never
    # sits on the frame.
    for axis, values in ((ax.xaxis, xs), (ax.yaxis, ys)):
        axis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(
                lambda v, _: (
                    "{:,.0f}".format(v) if v >= 1 else "{:g}".format(v)
                )
            )
        )
        axis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    def _padded(values, factor=3.0):
        lo, hi = min(values), max(values)
        return lo / factor, hi * factor

    ax.set_xlim(*_padded(xs))
    ax.set_ylim(*_padded(ys))
    ax.set_xlabel("CoreMark/MHz  (performance per clock)")
    ax.set_ylabel("CoreMark/Joule  (work per unit energy)")
    ax.set_title("Energy efficiency against performance per clock")
    ax.grid(True, which="both", alpha=0.3)

    prov = document.get("provenance", {})
    ax.text(
        0.0,
        -0.17,
        "{}, {}; activity: {}\nfrequency: {}\n{}".format(
            prov.get("platform", "?"),
            prov.get("stage", "?"),
            prov.get("activity", "?"),
            prov.get("frequency", "?"),
            prov.get("note", ""),
        ),
        transform=ax.transAxes,
        fontsize=7.5,
        va="top",
        color="0.35",
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    return len(points)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])

    with open(args.results) as f:
        document = json.load(f)

    n = plot(document, args.out)
    print("plot_results: {} point(s) -> {}".format(n, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
