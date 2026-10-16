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
number is its reg2reg group with its clock tree, at global route; each
block's is that block alone, likewise at its global route with its clock
tree (rows up to 2026-10-14 read the blocks at their place stage,
against an ideal clock). A run that
did not measure the blocks gives only a lower bound, drawn hollow.

The image carries no text beyond its axes and legend: the numbers and
what changed are the README's table, where they can be read and copied.
The runs are numbered on the horizontal axis and in the table, because a
date does not name a run: some days have two.

kpi_hist.png is every reg2reg endpoint's period of the last run that
recorded `histograms` (kpi_run.tcl's 10 ps bins), stacked, one colour for
the parent and one per block; the run before it is outlined. The mass
right of 2,000 ps is what remains. `--hist-only --bin 20 --log` redraws
it alone, from the json, in a second.

The chart starts at the first run below START_BELOW_PS. The runs before
it, tens of nanoseconds of clock-tree and abstraction artefacts, would
take the whole axis and draw every later change as a flat line; they
stay in the table, unnumbered. From there the range is about ten times,
so the axis is linear and a change of a few hundred picoseconds shows.
"""

import argparse
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

# the period every part has to reach; kpi_hist.png counts the endpoints above it
GOAL_PS = 2000
# kpi_hist.png's bin width: a multiple of the json's (10 ps)
HIST_BIN_PS = 50

TABLE_BEGIN = "<!-- kpi-table begin: written by kpi.py -->"
TABLE_END = "<!-- kpi-table end -->"
WORST_BEGIN = "<!-- kpi-worst begin: written by kpi.py -->"
WORST_END = "<!-- kpi-worst end -->"


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


def rebin(h, width):
    """A part's histogram {bin_ps, from_ps, counts} as {left edge: count} at
    `width` ps, a multiple of the recorded bin, on a grid aligned to multiples
    of `width`, so every part's bins line up."""
    out = {}
    for i, c in enumerate(h["counts"]):
        edge = h["from_ps"] + i * h["bin_ps"]
        key = edge - edge % width
        out[key] = out.get(key, 0) + c
    return out


def above(h, ps):
    """Endpoints whose period is above `ps`; the bin holding `ps` counts whole."""
    return sum(
        c
        for i, c in enumerate(h["counts"])
        if h["from_ps"] + (i + 1) * h["bin_ps"] > ps
    )


WORST_LINE = re.compile(r"^reg2reg\s+-?[\d.]+ ps\s+(\S+) -> (\S+)", re.M)
PERIOD_LINE = re.compile(r"reg2reg min period (\d+) ps")
HIST_LINE = re.compile(r"reg2reg endpoints bin (\d+) ps from (-?\d+) ps: ([\d ]+)")


def read_worst(text):
    """The worst reg2reg path in a part's kpi_run.tcl output; `what`, the
    path in words, is written by hand."""
    m, p = WORST_LINE.search(text), PERIOD_LINE.search(text)
    if not m or not p:
        raise SystemExit("no reg2reg path in the KPI output")
    return {
        "period_ps": int(p.group(1)),
        "from": m.group(1),
        "to": m.group(2),
        "what": "",
    }


def read_histogram(text):
    """The endpoint histogram in a part's kpi_run.tcl output, as kpi.json keeps it."""
    m = HIST_LINE.search(text)
    if not m:
        raise SystemExit(
            "no 'reg2reg endpoints' line: an output from before the histograms"
        )
    return {
        "bin_ps": int(m.group(1)),
        "from_ps": int(m.group(2)),
        "counts": [int(c) for c in m.group(3).split()],
    }


def legend(part, hist, worst):
    """A part's legend entry: its worst period, and its endpoints above the goal."""
    head = f"{part}: worst {worst['period_ps']:,} ps, " if worst else f"{part}: "
    return head + f"{above(hist, GOAL_PS):,} above {GOAL_PS:,} ps"


def draw_hist(runs, out, width=HIST_BIN_PS, log=False):
    """Every reg2reg endpoint's period of the last run that recorded
    histograms, stacked: one colour for the parent and one per block, so a
    bar says where the paths at that period are. The run before it that
    recorded histograms is outlined, its total. The mass right of the goal
    line is what remains to be done."""
    with_hist = [r for r in runs if r.get("histograms")]
    if not with_hist:
        return False
    hists = with_hist[-1]["histograms"]
    worst = with_hist[-1].get("worst_paths", {})
    parts = [p for p in ["parent"] + block_names(runs) if p in hists]
    parts += sorted(set(hists) - set(parts))
    rebinned = {p: rebin(hists[p], width) for p in parts}
    lo = min(min(r) for r in rebinned.values())
    hi = max(max(r) for r in rebinned.values())
    edges = list(range(lo, hi + width, width))

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = [0] * len(edges)
    for part in parts:
        counts = [rebinned[part].get(e, 0) for e in edges]
        ax.bar(
            edges,
            counts,
            width=width,
            bottom=bottom,
            align="edge",
            color="0.3" if part == "parent" else BLOCK_COLORS.get(part, OTHER_COLOR),
            label=legend(part, hists[part], worst.get(part)),
        )
        bottom = [b + c for b, c in zip(bottom, counts)]
    if len(with_hist) > 1:
        prev = with_hist[-2]["histograms"]
        total = {}
        for h in prev.values():
            for e, c in rebin(h, width).items():
                total[e] = total.get(e, 0) + c
        pe = sorted(total)
        ax.step(
            pe + [pe[-1] + width],
            [total[e] for e in pe] + [total[pe[-1]]],
            where="post",
            color="black",
            lw=0.8,
            label="previous run, all parts",
        )
    ax.axvline(GOAL_PS, color="black", ls=":", lw=1.5)
    ax.axvspan(GOAL_PS, max(hi + width, GOAL_PS + width), color="firebrick", alpha=0.07)
    if log:
        ax.set_yscale("log")
    ax.set_xlim(min(0, lo), max(hi + width, GOAL_PS + width))
    ax.set_xlabel("reg2reg endpoint period: SDC period minus slack (ps)")
    ax.set_ylabel("reg2reg endpoints" + (" (log)" if log else ""))
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    return True


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


def worst_table(runs):
    """Each part's worst reg2reg path of the last run that recorded them,
    with what it is in words."""
    with_worst = [r for r in runs if r.get("worst_paths")]
    if not with_worst:
        return None
    worst = with_worst[-1]["worst_paths"]
    parts = [p for p in ["parent"] + block_names(runs) if p in worst]
    parts += sorted(set(worst) - set(parts))
    lines = ["| part | period | worst reg2reg path | what it is |", "|---|---|---|---|"]
    for part in parts:
        w = worst[part]
        lines.append(
            "| %s | %s | `%s` → `%s` | %s |"
            % (
                part,
                f"{w['period_ps']:,}",
                w["from"],
                w["to"],
                w["what"].replace("|", "\\|"),
            )
        )
    return "\n".join(lines)


def write_table(readme, text, begin=TABLE_BEGIN, end=TABLE_END):
    with open(readme) as f:
        src = f.read()
    block = "%s\n%s\n%s" % (begin, text, end)
    pattern = re.escape(begin) + ".*?" + re.escape(end)
    if not re.search(pattern, src, re.S):
        raise SystemExit("%s: no %s markers" % (readme, begin))
    new = re.sub(pattern, lambda _: block, src, flags=re.S)
    with open(readme, "w") as f:
        f.write(new)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--hist-only",
        action="store_true",
        help="redraw kpi_hist.png alone, to iterate on it",
    )
    ap.add_argument("--bin", type=int, default=HIST_BIN_PS, help="histogram bin, ps")
    ap.add_argument("--log", action="store_true", help="histogram on a log scale")
    ap.add_argument(
        "--histograms",
        nargs="+",
        metavar="PART=KPI_TXT",
        help="record these parts' <part>_kpi.txt histograms in the last run "
        "(the parent's part name is 'parent'), then draw",
    )
    args = ap.parse_args()
    path = os.path.join(HERE, "kpi.json")
    with open(path) as f:
        d = json.load(f)
    if args.histograms:
        run = d["runs"][-1]
        hists = run.setdefault("histograms", {})
        worst = run.setdefault("worst_paths", {})
        for spec in args.histograms:
            part, _, txt = spec.partition("=")
            with open(txt) as f:
                text = f.read()
            hists[part] = read_histogram(text)
            # a hand-written `what` survives re-reading the same path
            old = worst.get(part, {})
            worst[part] = read_worst(text)
            if (old.get("from"), old.get("to")) == (
                worst[part]["from"],
                worst[part]["to"],
            ):
                worst[part]["what"] = old.get("what", "")
        text = json.dumps(d, indent=2, ensure_ascii=False)
        # a histogram's counts on one line, not one line per bin
        text = re.sub(
            r'"counts": \[[\d,\s]*\]',
            lambda m: re.sub(r"\s+", " ", m.group(0))
            .replace("[ ", "[")
            .replace(" ]", "]"),
            text,
        )
        with open(path, "w") as f:
            f.write(text + "\n")
    hist = os.path.join(HERE, "kpi_hist.png")
    if draw_hist(d["runs"], hist, args.bin, args.log):
        print(hist)
    if args.hist_only:
        return
    out = os.path.join(HERE, "kpi.png")
    draw(d["runs"], d["target_ps"], out)
    print(out)
    readme = os.path.join(HERE, "README.md")
    write_table(readme, table(d["runs"]))
    worst = worst_table(d["runs"])
    if worst:
        write_table(readme, worst, WORST_BEGIN, WORST_END)
    print(readme)


if __name__ == "__main__":
    main()
