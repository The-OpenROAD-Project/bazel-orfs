"""Regenerate the estimation ladder README and its figures.

The figures changed shape along with the study.  The old plot put
runtime on a linear axis, which only worked while every rung landed
within one order of magnitude of the others; the ladder now spans
roughly 0.02 s to several hundred seconds, so runtime is drawn on a log
axis and every "evenly spread" claim in the study is made in log space
too.

Three things are plotted, per design:

  1. accuracy against runtime -- the Pareto front rung B actually
     measured, with the rung A archive behind it as a reminder of how
     much of the space was explored to find those points;
  2. rank correlation against runtime -- whether a rung ranks the
     near-critical paths correctly, which is the question that matters
     when the estimate is used to decide what to fix;
  3. the bias/spread decomposition -- which rungs are merely offset
     (and so correctable by calibration) and which are genuinely noisy.

With --pr-body the same content is written with the image links
rewritten to absolute URLs, because GitHub does not resolve relative
image paths in a pull request body.
"""

import argparse
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

DESIGNS = [
    ("multiplier", "multiplier (simple)"),
    ("multiplier_top", "multiplier_top (macro array)"),
]

MAIN_PLOT = "pareto_plot.png"
BIAS_PLOT = "bias_spread.png"

FRONT_COLUMNS = [
    "runtime_s",
    "mean_rel_err",
    "kendall_tau",
    "bias",
    "spread",
    "worst_recall",
]


def rung_label(env):
    """A short description of which rungs of the ladder a config used."""
    if str(env.get("RUN_PLACE", "0")) != "1":
        return "synth only"
    # "place" is the base of every remaining rung, and naming it matters:
    # falling through to a generic label made a 90s global placement read
    # as the 0.02s synthesis rung.
    parts = ["place"]
    # Whether the macros were placed is the most consequential thing
    # about a configuration on a macro design, and its absence from the
    # label made several front rungs unreadable.
    if str(env.get("RUN_MACRO_PLACE", "1")) != "1":
        parts.append("NO macro place")
    if True:
        if str(env.get("PLACE_IOS", "0")) == "1":
            parts.append("place_ios")
        if str(env.get("GPL_TIMING_DRIVEN", "0")) == "1":
            parts.append("TD")
        if str(env.get("GPL_ROUTABILITY_DRIVEN", "0")) == "1":
            parts.append("RD")
        if str(env.get("GPL_VIRTUAL_CTS", "0")) == "1":
            parts.append("vCTS")
        mode = env.get("CLOCK_MODE", "none")
        if mode == "real":
            parts.append("CTS")
        elif mode == "propagated":
            parts.append("prop")
        if str(env.get("RUN_REPAIR_DESIGN", "0")) == "1":
            parts.append("rd")
        if str(env.get("RUN_GRT", "0")) == "1":
            parts.append(f"GRT({env.get('GRT_ITERATIONS', '?')})")
        if str(env.get("RUN_REPAIR_TIMING", "0")) == "1":
            parts.append("rt")
    return ", ".join(parts)


def load(directory, design):
    front_path = os.path.join(directory, f"runtime_front_{design}.json")
    archive_path = os.path.join(directory, f"archive_{design}.json")
    front = json.load(open(front_path)) if os.path.exists(front_path) else None
    archive = json.load(open(archive_path)) if os.path.exists(archive_path) else None
    return front, archive


def ground_truth_runtime(path):
    if not os.path.exists(path):
        return None
    return json.load(open(path)).get("runtime_s")


def plot_fronts(directory, data, gt_runtimes):
    fig, axes = plt.subplots(
        len(DESIGNS), 2, figsize=(13, 5 * len(DESIGNS)), squeeze=False
    )
    for row, (design, title) in enumerate(DESIGNS):
        front, archive = data[design]
        for col, (key, ylabel) in enumerate(
            [
                ("mean_rel_err", "mean relative error"),
                ("kendall_tau", "Kendall tau (rank correlation)"),
            ]
        ):
            ax = axes[row][col]
            if front:
                measured = front["measured"]
                ax.scatter(
                    [m["runtime_s"] for m in measured],
                    [m[key] for m in measured],
                    s=18,
                    color="0.7",
                    label="measured",
                )
                pts = sorted(front["front"], key=lambda p: p["runtime_s"])
                # The front is defined on (runtime, error).  Joining the
                # same points in the rank-correlation panel would draw a
                # frontier that does not exist there -- tau is not what
                # they were selected for, and it does not move
                # monotonically along them -- so only the error panel
                # gets a line, and only it carries the labels.
                if key == "mean_rel_err":
                    ax.plot(
                        [p["runtime_s"] for p in pts],
                        [p[key] for p in pts],
                        "o-",
                        color="tab:blue",
                        label="Pareto front",
                    )
                    for p in pts:
                        ax.annotate(
                            rung_label(p["env"]),
                            (p["runtime_s"], p[key]),
                            fontsize=6,
                            alpha=0.8,
                            xytext=(4, 3),
                            textcoords="offset points",
                        )
                else:
                    ax.scatter(
                        [p["runtime_s"] for p in pts],
                        [p[key] for p in pts],
                        s=42,
                        color="tab:blue",
                        zorder=3,
                        label="on the runtime/error front",
                    )
            gt = gt_runtimes.get(design)
            if gt:
                ax.axvline(
                    gt,
                    linestyle="--",
                    color="tab:red",
                    label=f"ground truth flow ({gt:.0f}s)",
                )
            ax.set_xscale("log")
            ax.set_xlabel("runtime (s, log scale)")
            ax.set_ylabel(ylabel)
            ax.set_title(f"{title}: {ylabel}")
            ax.grid(alpha=0.3)
            ax.legend(fontsize=8)
    fig.tight_layout()
    out = os.path.join(directory, MAIN_PLOT)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def plot_bias_spread(directory, data):
    """Bias and spread side by side.

    The point of separating them: a rung with a large bias but a small
    spread is wrong by a constant, which a calibration term can remove.
    A rung with a small bias and a large spread is not correctable that
    way, no matter how appealing its mean relative error looks.
    """
    fig, axes = plt.subplots(
        1, len(DESIGNS), figsize=(6.5 * len(DESIGNS), 5), squeeze=False
    )
    for col, (design, title) in enumerate(DESIGNS):
        ax = axes[0][col]
        front, _ = data[design]
        if front:
            pts = sorted(front["front"], key=lambda p: p["runtime_s"])
            idx = range(len(pts))
            ax.errorbar(
                list(idx),
                [p["bias"] for p in pts],
                yerr=[p["spread"] for p in pts],
                fmt="o",
                capsize=4,
                color="tab:purple",
            )
            ax.axhline(0.0, color="0.4", linewidth=1)
            ax.set_xticks(list(idx))
            ax.set_xticklabels(
                [f"{p['runtime_s']:.2g}s\n{rung_label(p['env'])}" for p in pts],
                rotation=45,
                ha="right",
                fontsize=7,
            )
        ax.set_ylabel("signed relative error (bar = 1 sd)")
        ax.set_title(f"{title}: bias and spread")
        ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    out = os.path.join(directory, BIAS_PLOT)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def front_table(front):
    if not front:
        return "_No measured front yet._"
    rows = []
    for p in sorted(front["front"], key=lambda p: p["runtime_s"]):
        row = {"rungs": rung_label(p["env"])}
        row.update({c: p.get(c) for c in FRONT_COLUMNS})
        rows.append(row)
    return pd.DataFrame(rows).to_markdown(index=False, floatfmt=".4g")


def spread_note(front):
    """State plainly whether the front is actually filled -- and, when it
    is not, whether the hole is something a bigger budget would close.

    The ladder is quantised: skipping placement costs milliseconds,
    running it costs seconds, and the space contains nothing in between.
    A gap straddling that boundary is a property of the ladder, not a
    failure of the search, and calling it a hole would misdescribe the
    result.  The distinction is made from measurements rather than from
    a model -- if dozens of placed configurations were timed and the
    fastest still sits above the gap, that is the evidence.
    """
    if not front:
        return ""
    pts = sorted(front["front"], key=lambda p: p["runtime_s"])
    if len(pts) < 2:
        return ""
    logs = [math.log10(max(p["runtime_s"], 1e-6)) for p in pts]
    span = logs[-1] - logs[0]
    gaps = [(b - a) / span for a, b in zip(logs, logs[1:])] if span > 0 else [0.0]
    worst = max(gaps)
    head = (
        f"{len(pts)} front points across "
        f"{10 ** logs[0]:.3g}s to {10 ** logs[-1]:.3g}s"
    )
    if worst <= 0.15:
        return f"{head}; widest normalized gap {worst:.3f}, within the 0.15 target."

    i = gaps.index(worst)
    lo, hi = pts[i], pts[i + 1]
    placed = [
        m
        for m in front.get("measured", [])
        if str(m["env"].get("RUN_PLACE", "0")) == "1"
    ]
    crosses_placement = (
        str(lo["env"].get("RUN_PLACE", "0")) != "1"
        and str(hi["env"].get("RUN_PLACE", "0")) == "1"
    )
    if crosses_placement and placed:
        fastest = min(m["runtime_s"] for m in placed)
        return (
            f"{head}. The widest gap ({worst:.3f}) spans "
            f"{lo['runtime_s']:.3g}s to {hi['runtime_s']:.3g}s and is "
            f"structural rather than unexplored: it separates the "
            f"configurations that skip placement from those that run it. "
            f"Of {len(placed)} placed configurations timed here the "
            f"fastest took {fastest:.3g}s, so there is no cheap-but-placed "
            f"estimate to be found in between -- the choice is binary."
        )
    return (
        f"{head}; widest normalized gap {worst:.3f}, so **a gap exceeds** "
        f"the 0.15 target and the budget did not fill it."
    )


def calibration_section(directory, image_prefix=""):
    """The transfer test, reported with its own yardstick.

    The estimator is optimistic by close to a constant fraction, so
    multiplying by one number removes most of the error.  Fitting that
    number against the ground truth it is then scored on measures the
    free parameter and nothing else, so the constant here is fitted on
    one design and applied to the other, and the oracle column says what
    a constant fitted on the target itself would have managed.  A rung
    whose transferred error sits near its oracle has a bias that belongs
    to the method; one whose transferred error is worse than its raw
    error has a bias that belongs to the design.
    """
    path = os.path.join(directory, "calibration_transfer.json")
    if not os.path.exists(path):
        return []
    data = json.load(open(path))
    fit, apply_to = data["fit_design"], data["apply_design"]
    rows = []
    for r in data["rungs"]:
        rows.append(
            {
                "rung": r["rung"],
                "scale": r["scale_fitted_on_" + fit],
                "raw err": r["raw_err"],
                "transferred": r["transferred_err"],
                "oracle": r["oracle_err"],
                "helped": "yes" if r["transferred_err"] < r["raw_err"] else "no",
            }
        )
    table = pd.DataFrame(rows).to_markdown(index=False, floatfmt=".4g")
    return [
        "## Does the bias transfer between designs?",
        "",
        f"The scale factor is fitted on `{fit}` and applied unchanged to",
        f"`{apply_to}`, which never contributed to it. **oracle** is what a",
        f"constant fitted on `{apply_to}`'s own ground truth would have",
        "achieved -- the ceiling the transferred number is measured against,",
        "not a result in itself.",
        "",
        table,
        "",
        "Rank correlation is absent from this table on purpose: it is",
        "invariant under a positive scale factor, so calibration cannot",
        "change the order the paths come out in, only how wrong the numbers",
        "are.",
        "",
    ]


def render(data, gt_runtimes, image_prefix="", image_suffix="", directory="."):
    out = ["# Estimation Ladder", ""]
    out += [
        "How accurately can early flow stages estimate the minimum clock period",
        "of the near-critical reg2reg paths, compared to a global-routed ground",
        "truth -- and at what runtime cost?",
        "",
        "Synthesis-only timing is optimistic: it sees no wires, and on a design",
        "with macros it does not see the clock tree either, so macro clock",
        "insertion latency lands straight in the estimated period. Adding early",
        "placement, a clock tree, resizing and global routing buys that back at",
        "increasing runtime -- the estimation ladder.",
        "",
        "Runtimes come from a separate measurement pass that runs one estimator",
        "at a time, so they are not contaminated by contention between",
        "concurrent trials; accuracy comes from a much wider concurrent sweep,",
        "which contention does not affect. Runtime is plotted on a log axis",
        "because the ladder spans several orders of magnitude.",
        "",
        f"![Pareto Plot]({image_prefix}{MAIN_PLOT}{image_suffix})",
        "",
        f"![Bias and spread]({image_prefix}{BIAS_PLOT}{image_suffix})",
        "",
    ]
    for design, title in DESIGNS:
        front, archive = data[design]
        out += [f"## {title}", ""]
        gt = gt_runtimes.get(design)
        if gt:
            out += [f"Ground truth flow runtime: {gt:.0f} s.", ""]
        if archive:
            out += [f"Rung A explored {len(archive)} configurations.", ""]
        note = spread_note(front)
        if note:
            out += [note, ""]
        out += [front_table(front), ""]
    out += calibration_section(directory, image_prefix)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ground_truth_json")
    ap.add_argument("ground_truth_top_json")
    ap.add_argument(
        "--pr-body",
        metavar="URL_PREFIX",
        help=(
            "also write README.pr.md with image links rewritten to this "
            "absolute prefix (GitHub does not resolve relative image paths "
            "in a pull request body)"
        ),
    )
    args = ap.parse_args()

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.environ.get("PWD", ".")
    directory = os.path.join(ws, "test/estimation_ladder")

    gt_runtimes = {
        "multiplier": ground_truth_runtime(args.ground_truth_json),
        "multiplier_top": ground_truth_runtime(args.ground_truth_top_json),
    }
    data = {design: load(directory, design) for design, _ in DESIGNS}

    plot_fronts(directory, data, gt_runtimes)
    plot_bias_spread(directory, data)

    readme = render(data, gt_runtimes, directory=directory)
    with open(os.path.join(directory, "README.md"), "w") as f:
        f.write(readme + "\n")
    print("Wrote README.md, " + MAIN_PLOT + ", " + BIAS_PLOT)

    if args.pr_body:
        prefix = args.pr_body if args.pr_body.endswith("/") else args.pr_body + "/"
        # ?raw=true: a bare blob URL renders GitHub's HTML page for the
        # file, not the image itself, so the PR body would show a link
        # where the figure should be.
        body = render(
            data,
            gt_runtimes,
            image_prefix=prefix,
            image_suffix="?raw=true",
            directory=directory,
        )
        with open(os.path.join(directory, "README.pr.md"), "w") as f:
            f.write(body + "\n")
        print("Wrote README.pr.md")


if __name__ == "__main__":
    main()
