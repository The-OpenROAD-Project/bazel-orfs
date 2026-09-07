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


def fig_measured(artifact_csv, memory_csv, out):
    """What the change actually produced, per design.

    Two panels rather than one chart with two scales: compressed artifact
    size is a ratio and peak RSS is megabytes, and putting them on one axis
    would be the dual-axis mistake.
    """
    artifact = list(csv.DictReader(open(artifact_csv)))
    memory = list(csv.DictReader(open(memory_csv)))

    # Peak RSS before the change, measured the same way, per design.
    before_rss = {
        "ariane133_2_floorplan.odb": 280736,
        "black_parrot_2_floorplan.odb": 369562,
        "microwatt_2_floorplan.odb": 254148,
    }

    def short(name):
        name = name.replace(".odb", "")
        if name.endswith("_5_route"):
            return name[: -len("_5_route")] + " (routed)"
        return name.replace("_2_floorplan", "")

    fig, (left, right) = plt.subplots(1, 2, figsize=(10.5, 3.6))

    names = [short(r["design"]) for r in artifact]
    gains = [int(r["zstd_before"]) / int(r["zstd_after"]) for r in artifact]
    bars = left.barh(
        list(range(len(names))),
        gains,
        height=0.55,
        color=BLUE,
        edgecolor=SURFACE,
        linewidth=2,
    )
    left.axvline(1.0, color=GREY, linewidth=1)
    for index, (bar, gain) in enumerate(zip(bars, gains)):
        left.annotate(
            f"{gain:.2f}x",
            (gain, index),
            textcoords="offset points",
            xytext=(6, 0),
            va="center",
            color=INK,
            fontsize=9,
        )
    left.set_yticks(list(range(len(names))))
    left.set_yticklabels(names, color=INK, fontsize=9)
    left.invert_yaxis()
    left.set_xlim(0, max(gains) * 1.25)
    left.set_xlabel(
        "compressed .odb, times smaller (zstd -3)", color=INK_MUTED, fontsize=9
    )
    left.set_title("On the wire", color=INK, fontsize=11, loc="left")
    style(left)
    left.grid(axis="y", visible=False)

    rows = [r for r in memory if r["design"] in before_rss]
    labels = [short(r["design"]) for r in rows]
    before = [before_rss[r["design"]] / 1024 for r in rows]
    after = [float(r["peak_rss_kb"]) / 1024 for r in rows]
    positions = range(len(labels))
    right.barh(
        [p - 0.19 for p in positions],
        before,
        height=0.34,
        color=GREY,
        label="today",
        edgecolor=SURFACE,
        linewidth=2,
    )
    right.barh(
        [p + 0.19 for p in positions],
        after,
        height=0.34,
        color=BLUE,
        label="columns",
        edgecolor=SURFACE,
        linewidth=2,
    )
    for index, (was, is_now) in enumerate(zip(before, after)):
        right.annotate(
            f"-{100 * (was - is_now) / was:.1f}%",
            (is_now, index + 0.19),
            textcoords="offset points",
            xytext=(6, 0),
            va="center",
            color=INK,
            fontsize=9,
        )
    right.set_yticks(list(positions))
    right.set_yticklabels(labels, color=INK, fontsize=9)
    right.invert_yaxis()
    right.set_xlim(0, max(before) * 1.3)
    right.set_xlabel("peak RSS of read_db, MB", color=INK_MUTED, fontsize=9)
    right.set_title("In memory", color=INK, fontsize=11, loc="left")
    style(right)
    right.grid(axis="y", visible=False)
    right.legend(
        frameon=False,
        fontsize=9,
        labelcolor=INK,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.24),
    )

    fig.suptitle(
        "One table stored as columns: iterm_tbl",
        color=INK,
        fontsize=12,
        x=0.01,
        ha="left",
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
    fig_measured(
        "study/soa/artifact-gain.csv",
        "study/soa/memory-soa-storage.csv",
        out / "soa-measured.png",
    )


if __name__ == "__main__":
    main()
