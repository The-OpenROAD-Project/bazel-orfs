#!/usr/bin/env python3
"""Plot CoreMark/Joule against CoreMark/MHz from the pinned results.

Reads results.json, and optionally §A.1's committed commodity CSV, so
iterating on the presentation never re-runs a flow.

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

import silicon_band  # noqa: E402
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def plot(document, out_path, commodity=None):
    points = document["points"]
    if not points:
        raise ValueError("no points to plot")

    fig, ax = plt.subplots(figsize=(7.5, 5.5))

    # Two regions, drawn first so every measured point sits on top of
    # them, and drawn as regions rather than markers because neither is
    # a measurement of the same thing this study measures.
    #
    # The lower one is where Appendix A's commodity cores sit: measured at
    # the wall plug and attributed by the slope of watts against active
    # core count, at a boundary its provenance states as "core and its
    # private caches" -- the same boundary this study reports. Measured
    # rather than apportioned, on real N7, Intel 7 and N4 silicon
    # against a predictive 7 nm kit at its best-case corner.
    #
    # The upper one is the observation that follows from it: above those
    # parts, at their performance per clock, there is no CPU at all --
    # not in this study, not in §A.1, not in the literature series. It
    # is drawn because an empty region is a result when the axes are
    # this wide, and because it is the region a core would have to reach
    # to be a major advance rather than a better point on a known curve.
    if commodity:
        ax.add_patch(
            plt.Rectangle(
                (commodity["x_min"], commodity["y_min"]),
                commodity["x_max"] - commodity["x_min"],
                commodity["y_max"] - commodity["y_min"],
                facecolor="tab:purple",
                alpha=0.16,
                edgecolor="tab:purple",
                linewidth=1.0,
                linestyle="--",
                zorder=1,
                label="x86 / Arm, one core + L1 measured (App. A, %d parts)"
                % commodity["parts"],
            )
        )

    # Split the measured series by whether the point meets §3.1's
    # boundary. A filled marker hardened its L1; a hollow one hardened no
    # memory at all and got a free, perfect one instead. Drawing them the
    # same would let the figure imply four measurements of the same kind,
    # which is the single thing this study is most at risk of being read
    # as saying.
    def meets_boundary(p):
        return p.get("boundary", "").startswith("core + L1")

    # Kept for the axis limits and the per-point labels below: the split
    # is how the series is drawn, not how it is measured.
    xs = [p["coremark_per_mhz"] for p in points]
    ys = [p["coremark_per_joule"] for p in points]

    met = [p for p in points if meets_boundary(p)]
    unmet = [p for p in points if not meets_boundary(p)]

    if unmet:
        ax.scatter(
            [p["coremark_per_mhz"] for p in unmet],
            [p["coremark_per_joule"] for p in unmet],
            s=70,
            facecolors="none",
            edgecolors="tab:blue",
            linewidths=1.6,
            zorder=3,
            label="asap7, grt, core only -- no memory hardened",
        )
    if met:
        ax.scatter(
            [p["coremark_per_mhz"] for p in met],
            [p["coremark_per_joule"] for p in met],
            s=70,
            color="tab:blue",
            zorder=3,
            label="asap7, grt, core + L1 hardened",
        )
        # §5.11: 2σ over the placement-seed ensemble, where a point has
        # one. A point without a bar has not been measured for spread,
        # which is different from having none.
        with_bars = [p for p in met if p.get("coremark_per_joule_2sigma")]
        if with_bars:
            ax.errorbar(
                [p["coremark_per_mhz"] for p in with_bars],
                [p["coremark_per_joule"] for p in with_bars],
                yerr=[p["coremark_per_joule_2sigma"] for p in with_bars],
                fmt="none",
                ecolor="tab:blue",
                elinewidth=1.2,
                capsize=4,
                zorder=2,
            )
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
                lambda v, _: ("{:,.0f}".format(v) if v >= 1 else "{:g}".format(v))
            )
        )
        axis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    def _padded(values, factor=3.0):
        lo, hi = min(values), max(values)
        return lo / factor, hi * factor

    all_x = (
        xs
        + [p["coremark_per_mhz"] for p in document.get("pending", [])]
        + [r["coremark_per_mhz"] for r in document.get("references", [])]
    )
    ax.set_xlim(*_padded(all_x))
    ax.set_ylim(min(ys) / 6.0, max(ys) * 6.0)

    # The empty region, once the y limit exists to bound it.
    if commodity:
        top = ax.get_ylim()[1]
        if top > commodity["y_max"]:
            ax.add_patch(
                plt.Rectangle(
                    (commodity["x_min"], commodity["y_max"]),
                    commodity["x_max"] - commodity["x_min"],
                    top - commodity["y_max"],
                    facecolor="tab:green",
                    alpha=0.08,
                    edgecolor="tab:green",
                    linewidth=1.0,
                    linestyle=":",
                    zorder=1,
                    label="no CPU here today",
                )
            )
            # High in the region and to its right: the reference ticks
            # along the top carry vertical labels near its left edge,
            # and the literature series sits just below it.
            ax.annotate(
                "no CPU here today",
                (commodity["x_max"] * 0.85, top * 0.45),
                fontsize=8.5,
                ha="center",
                va="center",
                color="tab:green",
            )
    ax.set_xlabel("CoreMark/MHz  (performance per clock)")
    ax.set_ylabel("CoreMark/Joule  (work per unit energy)")
    ax.set_title("Energy efficiency against performance per clock")
    ax.grid(True, which="both", alpha=0.3)

    # Configurations measured on one axis only. Drawn on the x-axis
    # rather than left out: a reader counting points should see every
    # core the study covers, and see which ones are unfinished.
    pending = document.get("pending", [])
    if pending:
        ax.scatter(
            [p["coremark_per_mhz"] for p in pending],
            [min(ys) / 2.5] * len(pending),
            marker="v",
            s=55,
            color="0.55",
            zorder=3,
        )
        for p in pending:
            ax.annotate(
                "{} ({})\nenergy pending".format(p["core"], p["isa"]),
                (p["coremark_per_mhz"], min(ys) / 2.5),
                textcoords="offset points",
                xytext=(9, -3),
                fontsize=8,
                color="0.4",
            )

    # The literature series: measured elsewhere, at another node, with
    # another toolchain, and -- unlike this study's points -- at a
    # boundary its source does not state. Its own colour and marker,
    # because reading the two as one trend would be wrong. The label
    # says "core" rather than "core + L1" for that reason: the paper
    # configures 64 KB L1s but never says whether the power it reports
    # includes them. See pin_results.py.
    lit = document.get("literature", [])
    if lit:
        ax.scatter(
            [r["coremark_per_mhz"] for r in lit],
            [r["coremark_per_joule"] for r in lit],
            s=70,
            marker="s",
            facecolors="none",
            edgecolors="tab:red",
            linewidths=1.6,
            zorder=3,
            label="GF 22 FDX, core, boundary unstated (CF'25)",
        )
        # The three points sit within a factor of two of each other on
        # both axes, so a single offset direction overlaps the labels.
        # Fan them out left-above, below, right-above in x order.
        placements = [(-9, 8, "right"), (0, -18, "center"), (9, 8, "left")]
        for i, r in enumerate(sorted(lit, key=lambda r: r["coremark_per_mhz"])):
            dx, dy, ha = placements[i % len(placements)]
            ax.annotate(
                r["name"],
                (r["coremark_per_mhz"], r["coremark_per_joule"]),
                textcoords="offset points",
                xytext=(dx, dy),
                fontsize=8,
                ha=ha,
                color="tab:red",
            )

    # Published CoreMark/MHz for cores this study has not measured, drawn
    # as ticks along the top. No y-coordinate, because the literature
    # does not publish energy at a stated boundary -- see pin_results.py.
    # They answer "where does this sit" on performance per clock, which
    # is the axis that reads across processes.
    references = document.get("references", [])
    if references:
        top = max(ys) * 1.45
        for r in references:
            ax.plot(
                [r["coremark_per_mhz"]] * 2,
                [top * 0.82, top],
                color="0.6",
                linewidth=1.1,
                zorder=2,
            )
            ax.annotate(
                r["name"],
                (r["coremark_per_mhz"], top),
                textcoords="offset points",
                xytext=(0, 3),
                fontsize=6.5,
                rotation=90,
                ha="center",
                va="bottom",
                color="0.4",
            )

    # After every series is drawn, not before: a legend built early
    # silently omits whatever is plotted after it, and the series most
    # likely to be added later is the one a reader most needs named.
    ax.legend(loc="upper left", fontsize=7.5, framealpha=0.9)

    prov = document.get("provenance", {})
    ax.text(
        0.0,
        -0.17,
        "{}, {}; activity: {}\ncorner: {}\nfrequency: {}\nboundary: {}\n"
        "{}".format(
            prov.get("platform", "?"),
            prov.get("stage", "?"),
            prov.get("activity", "?"),
            prov.get("corner", "?"),
            prov.get("frequency", "?"),
            prov.get("boundary", "?"),
            prov.get("note", "")
            + (
                "\nGrey ticks: published CoreMark/MHz for cores not measured "
                "here. No energy figure is shown for them -- the literature "
                "does not publish it at a stated boundary."
                if references
                else ""
            ),
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
    parser.add_argument(
        "--silicon",
        help="Appendix A's silicon.json. Draws the region its measured cores "
        "occupy, and the empty region above it.",
    )
    args = parser.parse_args(argv[1:])

    with open(args.results) as f:
        document = json.load(f)

    band = None
    if args.silicon:
        band = silicon_band.band(silicon_band.read(args.silicon))
    n = plot(document, args.out, band)
    print("plot_results: {} point(s) -> {}".format(n, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
