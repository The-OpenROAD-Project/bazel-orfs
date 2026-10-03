#!/usr/bin/env python3
"""Draw the KPI: XiangShan's minimum clock period over time, against the target.

    python3 test/coremark_joule/designs/asap7/xiangshan/kpi.py

Reads kpi.json beside it, writes kpi.png and rewrites the table between
the kpi-table markers in README.md. Add a row to the json when a change
moves the number, re-run this, commit all three.

The red series is the design's minimum clock period, the KPI: the largest
of the parent's period and each block's, since the design is only as fast
as its slowest part. The parent and each block are drawn dashed beneath
it, each a period that has to be at or below the design's. The parent's
number is its reg2reg group with its clock tree; each block's is that
block alone at its own place stage, against an ideal clock. A run that
did not measure the blocks gives only a lower bound, drawn hollow.

The image carries no text beyond its axes and legend: the numbers and
what changed are the README's table, where they can be read and copied.
The runs are numbered on the horizontal axis and in the table, because a
date does not name a run: some days have two.

The chart starts at the first run below START_BELOW_PS. The runs before
it, tens of nanoseconds of clock-tree and abstraction artefacts, would
take the whole axis and draw every later change as a flat line; they
stay in the table, unnumbered. From there the range is about ten times,
so the axis is linear and a change of a few hundred picoseconds shows.
"""

import json
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# the blocks, in the order they are drawn and tabulated, with a colour each
BLOCK_COLORS = {
    "Frontend": "#6baed6",
    "MemBlock": "#2171b5",
    "CoupledL2": "#d94801",
    "VecRegionModule": "#238b45",
    "FltRegionModule": "#807dba",
    "Region_1": "#807dba",
}
# a block the table does not name is still drawn, in grey
OTHER_COLOR = "#737373"
# the chart starts at the first run whose design period is below this:
# the Frontend block's 14,114 ps, the last of the early artefacts
START_BELOW_PS = 14114

TABLE_BEGIN = "<!-- kpi-table begin: written by kpi.py -->"
TABLE_END = "<!-- kpi-table end -->"


def design_ps(run):
    """The design is as fast as its slowest part: the parent or a block."""
    return max([run["parent_ps"]] + list(run.get("blocks", {}).values()))


def block_names(runs):
    return [
        n for n in BLOCK_COLORS if any(n in r.get("blocks", {}) for r in runs)
    ] + sorted({n for r in runs for n in r.get("blocks", {})} - set(BLOCK_COLORS))


def first_drawn(runs):
    return next(i for i, r in enumerate(runs) if design_ps(r) < START_BELOW_PS)


def draw(runs, target, out):
    start = first_drawn(runs)
    drawn = runs[start:]
    xs = list(range(1, len(drawn) + 1))

    fig, ax = plt.subplots(figsize=(10, 5))

    for name in block_names(drawn):
        pts = [
            (x, r["blocks"][name])
            for x, r in zip(xs, drawn)
            if name in r.get("blocks", {})
        ]
        if not pts:
            continue
        ax.plot(
            [p[0] for p in pts],
            [p[1] for p in pts],
            "s--",
            color=BLOCK_COLORS.get(name, OTHER_COLOR),
            lw=1.2,
            ms=4,
            zorder=2,
            label=name,
        )
    ax.plot(
        xs,
        [r["parent_ps"] for r in drawn],
        "o--",
        color="0.3",
        lw=1.2,
        ms=4,
        zorder=2,
        label="parent",
    )

    # the design, red: the KPI
    design = [design_ps(r) for r in drawn]
    ax.plot(xs, design, "-", color="firebrick", lw=2.4, zorder=3, label="design (KPI)")
    for x, y, r in zip(xs, design, drawn):
        ax.plot(
            x,
            y,
            "o",
            ms=8,
            zorder=4,
            color="firebrick",
            markerfacecolor="firebrick" if r.get("blocks") else "white",
        )
    ax.axhline(target, color="black", ls=":", lw=1.5, label="target")

    ax.set_ylim(0, max(design) * 1.08)
    ax.set_xlim(0.5, len(drawn) + 0.5)
    ax.set_xticks(xs)
    ax.set_xlabel("run (see the table)")
    ax.set_ylabel("minimum clock period (ps)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(axis="y", alpha=0.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)

    fig.savefig(out, dpi=120, bbox_inches="tight")


def table(runs):
    """The runs as a markdown table, the numbers the chart draws."""
    start = first_drawn(runs)
    names = block_names(runs)
    head = ["#", "date", "design", "parent"] + names + ["change"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for i, r in enumerate(runs):
        blocks = r.get("blocks", {})
        design = f"{design_ps(r):,}"
        cells = [
            str(i - start + 1) if i >= start else "not drawn",
            r["date"],
            ("%s" if blocks else "≥ %s") % design,
            f"{r['parent_ps']:,}",
        ]
        cells += [f"{blocks[n]:,}" if n in blocks else "" for n in names]
        cells.append(r["note"].replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_table(readme, text):
    with open(readme) as f:
        src = f.read()
    block = "%s\n%s\n%s" % (TABLE_BEGIN, text, TABLE_END)
    pattern = re.escape(TABLE_BEGIN) + ".*?" + re.escape(TABLE_END)
    if not re.search(pattern, src, re.S):
        raise SystemExit("%s: no kpi-table markers" % readme)
    new = re.sub(pattern, lambda _: block, src, flags=re.S)
    with open(readme, "w") as f:
        f.write(new)


def main():
    with open(os.path.join(HERE, "kpi.json")) as f:
        d = json.load(f)
    out = os.path.join(HERE, "kpi.png")
    draw(d["runs"], d["target_ps"], out)
    print(out)
    readme = os.path.join(HERE, "README.md")
    write_table(readme, table(d["runs"]))
    print(readme)


if __name__ == "__main__":
    main()
