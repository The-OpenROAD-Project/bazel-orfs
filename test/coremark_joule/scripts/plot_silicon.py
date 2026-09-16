"""Plot how three shipping parts give up performance as cores are added.

This is the half of the silicon measurement that survives scrutiny. The
energy comparison does not -- see the chapter -- but the throttling
curves are internally consistent, distinguishable from each other, and
each corroborated by what is independently known about the part.

Two panels, because the interesting thing is the pair. Throughput alone
cannot tell frequency throttling from SMT contention; power alone
cannot tell a part that is holding an operating point from one that is
being clamped. Together they separate all three behaviours:

  * flat throughput and flat per-core power  -> one operating point
  * throughput falling only past the physical core count -> SMT sharing
  * throughput falling well before it, then power pinned at a ceiling
    while throughput keeps falling -> turbo stepping, then a power limit

The x axis is active cores or threads normalised to the part's physical
core count, so three parts of very different size can be read on one
pair of axes, and the 1.0 line marks where SMT can first contribute.
"""

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

STYLE = {
    "AMD": ("tab:orange", "o"),
    "Intel": ("tab:blue", "s"),
    "Qualcomm": ("tab:green", "^"),
}


def plot(document, out_path):
    parts = document["parts"]
    if not parts:
        raise ValueError("no parts to plot")

    fig, (ax_t, ax_p) = plt.subplots(2, 1, figsize=(8.0, 7.6), sharex=True)

    for part in parts:
        colour, marker = STYLE.get(part["vendor"], ("0.4", "x"))
        xs = [p["active"] / part["cores"] for p in part["sweep"]]
        label = "{} {} ({}, {} cores)".format(
            part["vendor"],
            part["part"].replace(part["vendor"] + " ", ""),
            part["node"],
            part["cores"],
        )
        ax_t.plot(
            xs,
            [100.0 * p["relative_throughput"] for p in part["sweep"]],
            marker=marker,
            markersize=4,
            linewidth=1.4,
            color=colour,
            label=label,
        )
        ax_p.plot(
            xs,
            [p["wall_w"] for p in part["sweep"]],
            marker=marker,
            markersize=4,
            linewidth=1.4,
            color=colour,
            label=label,
        )

    # Where SMT can first contribute. Left of it every added thread is a
    # new physical core, so a throughput fall there cannot be sharing.
    for ax in (ax_t, ax_p):
        ax.axvline(1.0, color="0.6", linestyle=":", linewidth=1.2, zorder=1)
        ax.grid(True, alpha=0.3)
    ax_t.annotate(
        "all physical cores busy;\nbeyond here a new thread\nshares a core",
        (1.0, 103),
        textcoords="offset points",
        xytext=(6, -2),
        fontsize=7.5,
        color="0.35",
        va="top",
    )

    ax_t.set_ylabel("per-core throughput\n(% of the part's own peak)")
    ax_t.set_title("How three parts give up performance as cores are added")
    ax_t.set_ylim(50, 104)
    ax_t.legend(fontsize=8, loc="lower left")

    ax_p.set_ylabel("total system power at the plug (W)")
    ax_p.set_xlabel("active threads / physical cores")
    # Log, because a 12 W laptop and a 412 W server share the panel, and
    # explicit ticks because the default log locator labels one decade
    # and leaves the reader to guess the rest.
    ax_p.set_yscale("log")
    ax_p.set_yticks([10, 20, 50, 100, 200, 400])
    ax_p.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: "{:,.0f}".format(v))
    )
    ax_p.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    # The power ceiling is the finding in this panel: the Xeon pins at
    # one number while its throughput keeps falling in the panel above.
    for part in parts:
        tail = [p["wall_w"] for p in part["sweep"][-3:]]
        if len(tail) == 3 and max(tail) - min(tail) < 1e-9:
            last = part["sweep"][-1]
            ax_p.annotate(
                "power pinned at {:,.0f} W\nwhile throughput still falls".format(
                    last["wall_w"]
                ),
                (last["active"] / part["cores"], last["wall_w"]),
                textcoords="offset points",
                xytext=(-12, 14),
                fontsize=7.5,
                ha="right",
                color=STYLE.get(part["vendor"], ("0.4",))[0],
            )

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--silicon", required=True, help="silicon.json")
    ap.add_argument("--out", required=True, help="where to write the figure")
    args = ap.parse_args()

    with open(args.silicon) as handle:
        document = json.load(handle)
    print("wrote", plot(document, args.out))


if __name__ == "__main__":
    main()
