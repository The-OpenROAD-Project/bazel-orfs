#!/usr/bin/env python3
"""Figures for the repair-policy study, from the results directory.

plots.py --results DIR --bands JSON --out DIR

windows_<design>_<step>.png   TNS gained per hundred-pass window of the
                              setup sweep, default beside a policy: the
                              shape that decides whether a stopping rule
                              can be safe (mock-alu cts: a plateau, then
                              a jackpot)
verdict_<policy>.png          per design, flow wall delta against
                              minimum-clock-period delta, pass/fail
                              from the verdict
"""

import argparse
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "repair_timing_runtime"))
import report  # noqa: E402
import verdict  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def window_gains(record, step):
    """[(window end pass, TNS gain ps)] over the main phase of the setup call."""
    got = record["substeps"].get(step)
    if not got:
        return []
    for index, call in enumerate(got.get("repair", [])):
        if call["kind"] not in ("setup_hold", "floorplan_setup"):
            continue
        rows = got["repair_rows"][index]
        main = [r for r in rows if r["iter"] != "final" and r["marker"] == "*"]
        at = {}
        for r in main:
            if r["iter"] % 100 == 0:
                at.setdefault(r["iter"], r["en_tns"])
        its = sorted(at)
        return [(its[k], at[its[k]] - at[its[k - 1]]) for k in range(1, len(its))]
    return []


def windows(records_by_arm, design, step, out, labels):
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    drew = False
    for i, (arm, label) in enumerate(labels.items()):
        rec = records_by_arm.get(arm)
        if not rec:
            continue
        g = window_gains(rec, step)
        if not g:
            continue
        xs = [x for x, _ in g]
        ys = [y for _, y in g]
        ax.bar(
            [x + (i - 0.5) * 30 for x in xs],
            ys,
            width=28,
            color=SERIES[i],
            label=label,
            edgecolor=SURFACE,
            linewidth=0.6,
        )
        drew = True
    if not drew:
        plt.close(fig)
        return False
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xlabel("pass (window ends)", color=INK, fontsize=9)
    ax.set_ylabel("TNS gained in the window (ps)", color=INK, fontsize=9)
    ax.set_title(
        "{} {}: what each hundred passes bought".format(design, step),
        color=INK,
        fontsize=10,
        loc="left",
    )
    ax.legend(frameon=False, fontsize=8)
    style(ax)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return True


def verdict_scatter(verdicts, policy, out):
    pts = [
        (
            v["wall_pct"],
            next(
                (
                    -d
                    for l, _, _, d, _, _ in v["axes"]
                    if l == "min clock period" and d is not None
                ),
                None,
            ),
            v["design"],
            v["dominated_or_tied"],
        )
        for v in verdicts
    ]
    pts = [p for p in pts if p[0] is not None and p[1] is not None]
    if not pts:
        return False
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    for wall, mp, name, ok in pts:
        ax.scatter(
            wall,
            mp,
            s=36,
            color=SERIES[0] if ok else SERIES[1],
            edgecolor=SURFACE,
            linewidth=1,
            zorder=3,
        )
        if abs(wall) > 3 or abs(mp) > 3 or not ok:
            ax.annotate(
                name,
                (wall, mp),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=7,
                color=INK,
            )
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.set_xlabel("flow wall delta vs default (%), - is faster", color=INK, fontsize=9)
    ax.set_ylabel("minimum clock period delta (ps), + is better", color=INK, fontsize=9)
    passed = sum(1 for p in pts if p[3])
    ax.set_title(
        "{}: {} of {} designs pass the dominance bar".format(policy, passed, len(pts)),
        color=INK,
        fontsize=10,
        loc="left",
    )
    style(ax)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--bands", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--base", default="base-p00670068")
    parser.add_argument(
        "--policies", nargs="+", default=["base-p0074", "base-p0069", "base-p0077"]
    )
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    with open(args.bands) as handle:
        bands = json.load(handle)
    written = []
    base = verdict.load_arm(args.results, args.base)
    for policy in args.policies:
        pol = verdict.load_arm(args.results, policy)
        vs = [
            verdict.design_verdict(base[d], pol[d], bands)
            for d in sorted(base)
            if d in pol
        ]
        name = "verdict_{}.png".format(policy.replace("base-", ""))
        if vs and verdict_scatter(
            vs, policy.replace("base-", ""), os.path.join(args.out, name)
        ):
            written.append(name)
    labels = {args.base: "default"}
    labels.update({p: p.replace("base-", "") for p in args.policies})
    for design in ("mock-alu", "riscv32i", "jpeg", "ibex", "sky130hd/riscv32i"):
        for step in ("4_1_cts", "5_1_grt"):
            by_arm = {
                a: (verdict.load_arm(args.results, a).get(design)) for a in labels
            }
            name = "windows_{}_{}.png".format(design.replace("/", "+"), step)
            if windows(by_arm, design, step, os.path.join(args.out, name), labels):
                written.append(name)
    for name in written:
        sys.stdout.write("wrote {}\n".format(os.path.join(args.out, name)))


if __name__ == "__main__":
    main()
