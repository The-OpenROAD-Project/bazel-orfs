#!/usr/bin/env python3
"""Plot the A/B result from a collected CSV.

Two figures, because the run answers two different questions:

  * inertness -- does the PR change the DEFAULT flow at all? Plotted as
    the per-sequence delta, where the "stock" bar being exactly zero is
    the result rather than an axis label.
  * pressure  -- does the effect grow as slack gets scarce? Plotted as
    delta versus clock scale.

Paths never enter the figures. The leaves are produced in scratch
directories that name a local user and machine, and this repository is
public.
"""

import argparse
import csv
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SEQUENCES = ["stock", "before", "after", "only"]

# Colour-blind-safe, and consistent across both figures.
ARM_COLOR = {"base": "#4C72B0", "pr": "#DD8452"}


def slug(design):
    """Design labels reached the CSV in two spellings (asap7/riscv32i and
    asap7_aes) because STUDY_DESIGN is free text. Normalise for filenames;
    a "/" silently became a directory that did not exist."""
    return design.replace("/", "_")


def load(path):
    rows = list(csv.DictReader(open(path)))
    by = {}
    for r in rows:
        by[(r["design"], r["period_scale"], r["sequence"], r["arm"])] = r
    return rows, by


def deltas(by, design, scale):
    """PR minus base, per sequence, for one design and clock scale."""
    out = {}
    for seq in SEQUENCES:
        b = by.get((design, scale, seq, "base"))
        p = by.get((design, scale, seq, "pr"))
        if not (b and p):
            continue
        out[seq] = {
            "wns": float(p["wns"]) - float(b["wns"]),
            "tns": float(p["tns"]) - float(b["tns"]),
            "insts": int(p["inst_count"]) - int(b["inst_count"]),
            "area": (float(p["design_area"]) - float(b["design_area"])) * 1e12,
        }
    return out


def fig_sequences(by, design, scale, out):
    d = deltas(by, design, scale)
    if not d:
        return False
    seqs = [s for s in SEQUENCES if s in d]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    for ax, key, label in zip(
        axes,
        ["wns", "tns", "area"],
        ["Δ WNS (ps)", "Δ TNS (ps)", "Δ area (µm²)"],
    ):
        vals = [d[s][key] for s in seqs]
        colors = ["#999999" if s == "stock" else "#DD8452" for s in seqs]
        ax.bar(seqs, vals, color=colors)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(label, fontsize=10)
        ax.tick_params(labelsize=8)
    fig.suptitle(
        f"{design} @ clock scale {scale} — PR 11320 minus origin/master\n"
        "positive Δ WNS/TNS is better; negative Δ area is better; "
        "'stock' is the default sequence",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return True


def fig_pressure(by, design, out):
    scales = sorted({k[1] for k in by if k[0] == design}, key=float)
    series = defaultdict(list)
    for scale in scales:
        d = deltas(by, design, scale)
        for seq in SEQUENCES:
            series[seq].append(d.get(seq, {}).get("wns"))
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for seq in SEQUENCES:
        ys = series[seq]
        if all(y is None for y in ys):
            continue
        ax.plot(scales, ys, marker="o", label=seq)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("clock scale (smaller = tighter)")
    ax.set_ylabel("Δ WNS (ps), PR minus master")
    ax.set_title(f"{design}: does the effect grow with timing pressure?", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv")
    ap.add_argument("-d", "--outdir", required=True)
    args = ap.parse_args()

    _, by = load(args.csv)
    designs = sorted({k[0] for k in by})
    for design in designs:
        scales = sorted({k[1] for k in by if k[0] == design}, key=float)
        for scale in scales:
            name = f"{args.outdir}/{slug(design)}_scale{scale}_sequences.png"
            if fig_sequences(by, design, scale, name):
                print(f"wrote {name}")
        if len(scales) > 1:
            name = f"{args.outdir}/{slug(design)}_pressure.png"
            fig_pressure(by, design, name)
            print(f"wrote {name}")


if __name__ == "__main__":
    main()
