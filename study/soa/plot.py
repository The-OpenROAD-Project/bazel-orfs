#!/usr/bin/env python3
"""Figures for the odb field-major / structure-of-arrays study.

Reads the CSVs written by transpose_measure.py and the slot layouts measured
by the SoaLayoutFacts tool, and writes the three PNGs the write-up cites.

Palette is Okabe-Ito, a published colour-vision-deficiency-safe qualitative
set: hues are assigned to tables in a fixed order and never cycled, so a
table keeps its colour across every figure.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Okabe-Ito, fixed order, with the orange darkened to #B26A00 so the set
# passes the palette validator's contrast check against a light surface as
# well as its CVD separation checks. sbox / iterm / box keep these hues
# across every figure; grey is a neutral for "today", not a category.
BLUE = "#0072B2"
ORANGE = "#B26A00"
GREEN = "#009E73"
VERMILLION = "#D55E00"
GREY = "#7F7F7F"

TABLE_COLOR = {"sbox": BLUE, "iterm": ORANGE, "box": GREEN}
TABLE_LABEL = {"sbox": "sbox_tbl", "iterm": "iterm_tbl", "box": "box_tbl"}

# Ink, never a series colour.
INK = "#1A1A1A"
INK_MUTED = "#606060"
SURFACE = "#FFFFFF"

# Measured by //src/odb/src/db:SoaLayoutFacts against the pinned OpenROAD
# revision the flow builds with. Segments sum to sizeof.
#   persistent  - fields the .odb actually carries
#   bookkeeping - offset_in_bytes_ + oid_, both derivable from the slot index
#   slack       - padding holes, plus the Rect/Oct union's 4 unused bytes
#   cached      - cached pointer, not saved; becomes its own array
#   sparse      - access-point map, empty on most slots; becomes a side table
LAYOUT = {
    "_dbBox": {
        "persistent": 36,
        "bookkeeping": 8,
        "slack": 4,
        "cached": 0,
        "sparse": 0,
    },
    "_dbSBox": {
        "persistent": 40,
        "bookkeeping": 8,
        "slack": 4,
        "cached": 0,
        "sparse": 0,
    },
    "_dbITerm": {
        "persistent": 40,
        "bookkeeping": 8,
        "slack": 8,
        "cached": 8,
        "sparse": 24,
    },
}
SEGMENTS = [
    ("persistent", BLUE, "persistent fields"),
    ("cached", GREEN, "cached pointer (own array)"),
    ("bookkeeping", ORANGE, "bookkeeping (derivable)"),
    ("slack", VERMILLION, "padding + union slack"),
    ("sparse", GREY, "access points (sparse side table)"),
]


# What a slot still costs once the derivable and sparse parts are gone.
def kept(name):
    return LAYOUT[name]["persistent"] + LAYOUT[name]["cached"]


def style(ax):
    """Recessive grid and axes; ink text."""
    ax.set_axisbelow(True)
    ax.grid(True, color="#E6E6E6", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#CCCCCC")
    ax.tick_params(colors=INK_MUTED, labelsize=9)


def load(csv_path):
    return list(csv.DictReader(open(csv_path)))


def fig_gain_vs_block(designs, out, codec="zstd", level="3"):
    """Gain against block size, one panel per design.

    The vertical marker is sbox_tbl's page size: a page-local layout is stuck
    there, which is why the block has to be decoupled from the page.
    """
    fig, axes = plt.subplots(
        1, len(designs), figsize=(4.6 * len(designs), 3.6), sharey=True
    )
    axes = [axes] if len(designs) == 1 else list(axes)

    for ax, (name, rows) in zip(axes, designs.items()):
        series = defaultdict(list)
        for r in rows:
            if r["codec"] == codec and r["level"] == level:
                series[r["table"]].append((int(r["block"]), float(r["gain"])))
        placed = []  # end-label y positions, to keep close labels legible
        for table in ("sbox", "iterm", "box"):
            pts = sorted(series.get(table, []))
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(
                xs,
                ys,
                color=TABLE_COLOR[table],
                linewidth=2,
                marker="o",
                markersize=5,
                markeredgecolor=SURFACE,
                markeredgewidth=1,
                label=TABLE_LABEL[table],
            )
            # Nudge an end label off any earlier one within a hair of it.
            dy = 0
            while any(abs(ys[-1] + dy - p) < 0.9 for p in placed):
                dy -= 1.0
            placed.append(ys[-1] + dy)
            ax.annotate(
                f"{ys[-1]:.1f}x",
                (xs[-1], ys[-1] + dy),
                textcoords="offset points",
                xytext=(6, 0),
                color=INK,
                fontsize=9,
                va="center",
            )
        ax.axvline(128, color=GREY, linewidth=1, linestyle=(0, (4, 3)))
        ax.annotate(
            "sbox page size",
            (128, ax.get_ylim()[1]),
            textcoords="offset points",
            xytext=(6, -12),
            color=INK_MUTED,
            fontsize=8,
        )
        ax.set_xscale("log", base=2)
        ax.set_xlabel("records per block", color=INK_MUTED, fontsize=9)
        ax.set_title(name, color=INK, fontsize=11, loc="left")
        style(ax)
        ax.set_xlim(right=xs[-1] * 2.2)

    axes[0].set_ylabel("compressed size, times smaller", color=INK_MUTED, fontsize=9)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.suptitle(
        f"Field-major byte order, gain against block size ({codec} -{level})",
        color=INK,
        fontsize=12,
        x=0.01,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"wrote {out}")


def fig_bytes_per_slot(out):
    """What each slot's bytes are spent on, per struct."""
    names = list(LAYOUT)
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    y = range(len(names))

    for key, color, label in SEGMENTS:
        left = [
            sum(
                LAYOUT[n][k]
                for k, _, _ in SEGMENTS[: [s[0] for s in SEGMENTS].index(key)]
            )
            for n in names
        ]
        widths = [LAYOUT[n][key] for n in names]
        ax.barh(
            list(y),
            widths,
            left=left,
            height=0.55,
            color=color,
            label=label,
            edgecolor=SURFACE,
            linewidth=2,  # 2px surface gap between segments
        )

    for i, n in enumerate(names):
        total = sum(LAYOUT[n].values())
        keep = kept(n)
        ax.annotate(
            f"{total} B  ->  {keep} B",
            (total, i),
            textcoords="offset points",
            xytext=(8, 0),
            color=INK,
            fontsize=9,
            va="center",
        )

    ax.set_yticks(list(y))
    ax.set_yticklabels(names, color=INK, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("bytes per table slot", color=INK_MUTED, fontsize=9)
    ax.set_xlim(right=max(sum(v.values()) for v in LAYOUT.values()) * 1.35)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.legend(
        frameon=False,
        fontsize=9,
        labelcolor=INK,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.30),
    )
    ax.set_title(
        "Where a slot's bytes go, and what field-major storage keeps",
        color=INK,
        fontsize=12,
        loc="left",
    )
    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"wrote {out}")


def fig_totals(designs, out, codec="zstd", level="3", block=8192):
    """Compressed bytes for the measured tables, today against field-major."""
    labels, today, after = [], [], []
    for name, rows in designs.items():
        sel = [
            r
            for r in rows
            if r["codec"] == codec and r["level"] == level and int(r["block"]) == block
        ]
        if not sel:
            continue
        labels.append(name)
        today.append(sum(int(r["aos_bytes"]) for r in sel) / 1e6)
        after.append(sum(int(r["soa_bytes"]) for r in sel) / 1e6)

    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    ax.bar(
        [i - 0.21 for i in x],
        today,
        width=0.4,
        color=GREY,
        label="today",
        edgecolor=SURFACE,
        linewidth=2,
    )
    ax.bar(
        [i + 0.21 for i in x],
        after,
        width=0.4,
        color=BLUE,
        label="field-major",
        edgecolor=SURFACE,
        linewidth=2,
    )
    for i, (a, b) in enumerate(zip(today, after)):
        ax.annotate(
            f"{a:.2f} MB",
            (i - 0.21, a),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            color=INK,
            fontsize=9,
        )
        ax.annotate(
            f"{b:.2f} MB\n{a / b:.2f}x smaller",
            (i + 0.21, b),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            color=INK,
            fontsize=9,
        )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, color=INK, fontsize=10)
    ax.set_ylabel(f"compressed MB ({codec} -{level})", color=INK_MUTED, fontsize=9)
    ax.set_ylim(top=max(today) * 1.35)
    style(ax)
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    ax.set_title(
        f"sbox_tbl + box_tbl + iterm_tbl, {block}-record blocks",
        color=INK,
        fontsize=12,
        loc="left",
    )
    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"wrote {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sweeps",
        nargs="+",
        help="design=path/to/sweep.csv, repeatable",
    )
    parser.add_argument("--outdir", default=".", help="where to write the PNGs")
    args = parser.parse_args()

    designs = {}
    for spec in args.sweeps:
        name, path = spec.split("=", 1)
        designs[name] = load(path)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    fig_gain_vs_block(designs, out / "soa-gain-vs-block.png")
    fig_bytes_per_slot(out / "soa-bytes-per-slot.png")
    fig_totals(designs, out / "soa-compressed-totals.png")


if __name__ == "__main__":
    main()
