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


# One figure per panel rather than a grid: a 2x2 tiling left every rung
# label overlapping its neighbours and unreadable.
def figure_names(design):
    return {
        "pareto": f"pareto_{design}.png",
        "ranking": f"ranking_{design}.png",
        "bias": f"bias_{design}.png",
    }


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


def _annotate_numbered(ax, pts, key):
    """Number the front points instead of labelling them in place.

    A rung label like "place, NO macro place, TD, RD, vCTS, CTS" cannot
    sit beside a marker at any figure size without colliding with its
    neighbours, so the plot carries an index and the README table --
    already sorted by runtime -- is the key.
    """
    for n, p in enumerate(pts, 1):
        ax.annotate(
            str(n),
            (p["runtime_s"], p[key]),
            fontsize=9,
            fontweight="bold",
            color="tab:blue",
            xytext=(6, 4),
            textcoords="offset points",
        )


def _ground_truth_line(ax, gt):
    if gt:
        ax.axvline(
            gt,
            linestyle="--",
            color="tab:red",
            label=f"full flow ({gt:.0f}s)",
        )


def plot_error(directory, design, title, front, gt):
    fig, ax = plt.subplots(figsize=(10, 6))
    if front:
        ax.scatter(
            [m["runtime_s"] for m in front["measured"]],
            [m["mean_rel_err"] for m in front["measured"]],
            s=22,
            color="0.72",
            label="measured",
        )
        pts = sorted(front["front"], key=lambda p: p["runtime_s"])
        ax.plot(
            [p["runtime_s"] for p in pts],
            [p["mean_rel_err"] for p in pts],
            "o-",
            color="tab:blue",
            label="Pareto front (numbered as in the table)",
        )
        _annotate_numbered(ax, pts, "mean_rel_err")
    _ground_truth_line(ax, gt)
    ax.set_xscale("log")
    ax.set_xlabel("runtime (s, log scale)")
    ax.set_ylabel("mean relative error")
    ax.set_title(f"{title}: accuracy vs runtime")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    out = os.path.join(directory, f"pareto_{design}.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)


def plot_ranking(directory, design, title, front, gt, n_paths):
    """Rank correlation and worst-path recall, with recall's chance line.

    Recall@10 is meaningless without it: picking 10 of n paths at random
    scores 10/n, so a rung at 0.10 on a 99-path design has no skill at
    all rather than a little.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax2 = ax.twinx()
    if front:
        pts = sorted(front["front"], key=lambda p: p["runtime_s"])
        ax.plot(
            [p["runtime_s"] for p in pts],
            [p["kendall_tau"] for p in pts],
            "o-",
            color="tab:blue",
            label="Kendall tau (left)",
        )
        _annotate_numbered(ax, pts, "kendall_tau")
        ax2.plot(
            [p["runtime_s"] for p in pts],
            [p["worst_recall"] for p in pts],
            "s--",
            color="tab:green",
            label="recall@10 (right)",
        )
    if n_paths:
        chance = 10.0 / n_paths
        ax2.axhline(
            chance,
            linestyle=":",
            color="tab:red",
            label=f"recall@10 by chance ({chance:.2f})",
        )
    _ground_truth_line(ax, gt)
    ax.set_xscale("log")
    ax.set_xlabel("runtime (s, log scale)")
    ax.set_ylabel("Kendall tau")
    ax2.set_ylabel("recall@10")
    ax2.set_ylim(-0.05, 1.05)
    ax.set_title(f"{title}: does the ladder rank the critical paths?")
    ax.grid(alpha=0.3)
    lines, labels = ax.get_legend_handles_labels()
    l2, lb2 = ax2.get_legend_handles_labels()
    # Below the axes: recall runs along the bottom of the plot, so an
    # in-axes legend sits on top of the data it is describing.
    ax.legend(
        lines + l2,
        labels + lb2,
        fontsize=9,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=4,
    )
    fig.tight_layout()
    out = os.path.join(directory, f"ranking_{design}.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)


def plot_bias(directory, design, title, front):
    """Bias and spread separately.

    A rung with a large bias but a small spread is wrong by a constant,
    which one number can remove.  A rung with a small bias and a large
    spread is not correctable that way however good its mean absolute
    error looks.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    if front:
        pts = sorted(front["front"], key=lambda p: p["runtime_s"])
        idx = list(range(1, len(pts) + 1))
        ax.errorbar(
            idx,
            [p["bias"] for p in pts],
            yerr=[p["spread"] for p in pts],
            fmt="o",
            capsize=5,
            color="tab:purple",
        )
        ax.axhline(0.0, color="0.4", linewidth=1)
        ax.set_xticks(idx)
        ax.set_xticklabels(
            [f"{n}\n{p['runtime_s']:.3g}s" for n, p in zip(idx, pts)], fontsize=9
        )
    ax.set_xlabel("front point (numbered as in the table)")
    ax.set_ylabel("signed relative error (bar = 1 sd)")
    ax.set_title(f"{title}: is the error an offset or is it scatter?")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    out = os.path.join(directory, f"bias_{design}.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)


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


def methods_section(path_counts):
    """Everything statistical, kept out of the way of the result.

    A reader who wants the answer should not have to work through rank
    correlation and cross-validation to reach it, and a reader who
    doubts the answer should be able to find exactly how it was
    established.  Those are different readers and they want different
    pages.
    """
    chance = ", ".join(
        f"{design}: {10.0 / n:.2f}" for design, n in sorted(path_counts.items()) if n
    )
    return [
        "---",
        "",
        "## How we measured it",
        "",
        "### The ground truth",
        "",
        "The flow is run properly -- floorplan, placement, CTS, global route --",
        "and the timing read off the result with propagated clocks and",
        "global-routing parasitics. Up to 100 reg2reg paths are sampled from",
        "the worst quarter of the period range, in ten buckets, so the sample",
        "is spread across the near-critical paths rather than piled on the",
        "single worst one. A *register* here can be a macro. The estimator has",
        "to report every sampled path: one it cannot find is an error, not a",
        "path to quietly drop, because dropping the awkward ones would make any",
        "configuration look good.",
        "",
        "The flow runtime it is compared against is the floorplan-through-",
        "global-route stages summed from their own logs. Synthesis is excluded",
        "from both sides, since both start from the same post-synthesis",
        "netlist.",
        "",
        "### Why runtime and accuracy are measured separately",
        "",
        "Accuracy is a property of the placement and the parasitics, so many",
        "estimators can run at once without affecting it. Runtime is not: eight",
        "concurrent runs measure contention between siblings as much as the",
        "settings under test. So there are two passes. The first sweeps the",
        "knob space concurrently and records accuracy only. The second re-runs",
        "selected configurations one at a time and times them, with whatever",
        "thread count ORFS hands the tool, three times over, taking the median",
        "and adding repeats when they disagree by more than 5%.",
        "",
        "The second pass chooses what to measure adaptively. Because the first",
        "pass already knows every configuration's accuracy, the only open",
        "question is whether a configuration is fast enough to matter, so it",
        "measures wherever a runtime model thinks a configuration might beat",
        "the best already timed at that accuracy.",
        "",
        "### The accuracy numbers",
        "",
        "- **mean relative error** -- the average of |estimate - truth| / truth",
        "  over the sampled paths.",
        "- **bias** and **spread** -- the average signed error, and the",
        "  variation around it. Reported separately because they mean different",
        "  things: an estimator that is wrong by a consistent amount can be",
        "  corrected with one number, and one that is wrong erratically cannot,",
        "  even when their mean relative errors match.",
        "- **Kendall tau** -- rank correlation between estimated and true path",
        "  order. 1 is perfect agreement, 0 is unrelated.",
        f"- **recall@10** -- of the ten truly worst paths, how many the",
        f"  estimator also puts in its worst ten. Chance level is ten divided",
        f"  by the number of sampled paths ({chance}); a rung at or below that",
        "  has no skill at all rather than a little.",
        "",
        "### The correction",
        "",
        "Ten families were fitted -- a multiplicative constant, an additive",
        "offset, an affine fit, a power law, quadratic and cubic polynomials,",
        "an isotonic fit, a Gaussian process, and Bayesian linear regression --",
        "and each was scored three ways: on the design it was fitted to, on",
        "held-out paths of that design, and on the *other* design entirely.",
        "Only the third number says anything, because a correction fitted",
        "against the ground truth it is then graded on is measuring its own",
        "free parameter.",
        "",
        "Every one of these reads only the estimate, and a function of the",
        "estimate alone cannot reorder the paths. So none of them can improve",
        "rank correlation or worst-path recall -- the ordering after correction",
        "is identical, which is checked rather than assumed. Fixing the order",
        "would need a per-path correction using features of each path, which is",
        "a different study.",
        "",
        "### What the numbers do not cover",
        "",
        "Two small designs, one of which is 400um square. The knob-to-outcome",
        "associations come from a sweep that concentrates its sampling near the",
        "best configurations, so they are suggestive rather than controlled",
        "experiments. The macro design's front rests on 14 timed",
        "configurations, and the simple design's search hit its budget before",
        "meeting its own spread criterion.",
        "",
        "### Reproducing it",
        "",
        "```sh",
        "bazel build //test/estimation_ladder:extract_ground_truth \\",
        "            //test/estimation_ladder:extract_ground_truth_top",
        "bazel run //test/estimation_ladder:optuna_study        # accuracy sweep",
        "bazel run //test/estimation_ladder:optuna_study_top",
        "bazel run //test/estimation_ladder:measure_runtime     # timed pass",
        "bazel run //test/estimation_ladder:measure_runtime_top",
        "bazel run //test/estimation_ladder:calibration_transfer",
        "bazel run //test/estimation_ladder:calibration_models",
        "bazel run //test/estimation_ladder:update-readme",
        "```",
        "",
    ]


def headline(data, gt_runtimes):
    """The result, for a reader who knows EDA and not statistics.

    Deliberately free of tau, bias, spread and Pareto vocabulary: those
    are how the result was established rather than what it says, and
    they live in the methods section at the bottom.
    """
    out = []
    for design, title in DESIGNS:
        front, _ = data[design]
        gt = gt_runtimes.get(design)
        if not (front and front["front"] and gt):
            continue
        placed = [
            p for p in front["front"] if str(p["env"].get("RUN_PLACE", "0")) == "1"
        ]
        if not placed:
            continue
        # The rung someone would actually choose: the cheapest one within
        # a percentage point of the best accuracy on offer, rather than
        # the most accurate at any price.
        best_err = min(p["mean_rel_err"] for p in placed)
        pick = min(
            (p for p in placed if p["mean_rel_err"] <= best_err + 0.01),
            key=lambda p: p["runtime_s"],
        )
        out.append(
            f"- **{title}**: the flow takes {gt:.0f}s. The estimator gets "
            f"within **{pick['mean_rel_err']:.1%}** of it in "
            f"**{pick['runtime_s']:.3g}s** -- about "
            f"**{gt / pick['runtime_s']:.0f}x faster**."
        )
    return out


def render(
    data, gt_runtimes, path_counts, image_prefix="", image_suffix="", directory="."
):
    out = ["# Estimation Ladder", ""]
    out += [
        "**How close can you get to the clock period the flow would give you,",
        "without running the flow?**",
        "",
        "The baseline throughout is running floorplan through global route and",
        "reading the timing off the result. Everything here is measured against",
        "that, because that is the thing you would otherwise have to do.",
        "",
    ]
    out += headline(data, gt_runtimes)
    out += [
        "",
        "### Why the estimate is off at all",
        "",
        "The estimator places cells but never routes them, so it works from",
        "straight-line wire estimates. The router builds longer wires than that",
        "-- detours, congestion, vias -- so every path comes out optimistic.",
        "That is what pre-route means, and it is not a defect.",
        "",
        "### The useful part: it is off by nearly the same amount everywhere",
        "",
        "The estimator is not erratic, it is consistently optimistic. Almost",
        "every path is short by close to the same amount, so **one correction",
        "term removes most of the error**, and a term worked out on one design",
        "still helps on another. Adding that correction to plain global",
        "placement beats an uncorrected run that also pays for a clock tree and",
        "global routing, at a fraction of the runtime. Much of what the",
        "expensive stages appear to buy is an offset you can subtract for free.",
        "",
        "The correction is worth more to the cheap rungs than the expensive",
        "ones. On rungs that are already accurate, a correction borrowed from",
        "another design makes them worse, because what is left of their error",
        "belongs to that particular design.",
        "",
        "### The limit: a good speedometer, a poor map",
        "",
        "It predicts the period well and it is poor at telling you *which*",
        "paths are critical. Of the ten genuinely worst paths, the estimator",
        "puts only one to three of them in its own worst ten on the macro",
        "design -- and picking at random would get one. Spending more runtime",
        "does not fix it: on the simple design the 0.012s synthesis-only",
        "estimate finds more of the worst paths than the 6.9s estimate that",
        "predicts the period twenty times more precisely.",
        "",
        "So for *what clock period will this close at*, the estimator works.",
        "For *which path do I go fix*, it does not replace the flow.",
        "",
        "### What did not help",
        "",
        "- `-place_ios`, letting placement move the IO pins: fastest rung,",
        "  worst accuracy.",
        "- `-virtual_cts`, a cheap stand-in clock tree: worse than doing",
        "  nothing about the clock at all.",
        "- `repair_timing` at its default setting: 48s of runtime, no",
        "  measurable change to the answer.",
        "- Fancier corrections. A cubic, an isotonic fit, a Gaussian process --",
        "  all fit the design they were tuned on better and all transfer to a",
        "  new design worse. The Gaussian process reaches zero error on its own",
        "  design, which is memorisation, and then does worse than no",
        "  correction at all on the other one.",
        "",
        "A real clock tree, by contrast, was worth it: it cut the error by a",
        "third for under two seconds, because it captures the insertion delay",
        "through the macros that an ideal clock hides.",
        "",
        "### One thing to know before copying a configuration",
        "",
        "Several of the fastest rungs skip the macro placer. Global placement",
        "does then position the macros itself, and their locations are real --",
        "but twelve of the hundred and twenty macro pairs end up overlapping,",
        "where the macro placer leaves none. That is serviceable to estimate",
        "timing from and impossible as a floorplan. These rungs are estimators,",
        "not placements.",
        "",
        "---",
        "",
        "## Results per design",
        "",
    ]
    for design, title in DESIGNS:
        front, archive = data[design]
        figs = figure_names(design)
        out += [f"## {title}", ""]
        gt = gt_runtimes.get(design)
        n_paths = path_counts.get(design)
        if gt:
            speed = ""
            if front and front["front"]:
                pts = sorted(front["front"], key=lambda p: p["runtime_s"])
                fastest, best = pts[0], pts[-1]
                speed = (
                    f" The cheapest rung on the front is {gt / fastest['runtime_s']:.0f}x "
                    f"faster than that at {fastest['mean_rel_err']:.1%} error, and the "
                    f"most accurate is {gt / best['runtime_s']:.0f}x faster at "
                    f"{best['mean_rel_err']:.1%}."
                )
            out += [
                f"Running the flow itself -- floorplan through global route, "
                f"the baseline this is all measured against -- takes "
                f"**{gt:.0f}s**.{speed}",
                "",
            ]
        if n_paths:
            out += [
                f"Sampled {n_paths} near-critical reg2reg paths. Recall@10 "
                f"by chance is {10.0 / n_paths:.2f}: a rung scoring at or "
                f"below that has no skill at picking the critical paths.",
                "",
            ]
        if archive:
            out += [f"Rung A explored {len(archive)} configurations.", ""]
        note = spread_note(front)
        if note:
            out += [note, ""]
        out += [front_table(front), ""]
        out += [
            f"![{title} accuracy]({image_prefix}{figs['pareto']}{image_suffix})",
            "",
            f"![{title} ranking]({image_prefix}{figs['ranking']}{image_suffix})",
            "",
            f"![{title} bias]({image_prefix}{figs['bias']}{image_suffix})",
            "",
        ]
    out += calibration_section(directory, image_prefix)
    out += methods_section(path_counts)
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

    # How many paths were sampled sets the chance baseline for recall@10.
    path_counts = {}
    for design, gt_path in (
        ("multiplier", args.ground_truth_json),
        ("multiplier_top", args.ground_truth_top_json),
    ):
        if os.path.exists(gt_path):
            path_counts[design] = len(json.load(open(gt_path))["paths"])

    for design, title in DESIGNS:
        front, _ = data[design]
        plot_error(directory, design, title, front, gt_runtimes.get(design))
        plot_ranking(
            directory,
            design,
            title,
            front,
            gt_runtimes.get(design),
            path_counts.get(design),
        )
        plot_bias(directory, design, title, front)

    readme = render(data, gt_runtimes, path_counts, directory=directory)
    with open(os.path.join(directory, "README.md"), "w") as f:
        f.write(readme + "\n")
    print(f"Wrote README.md and {3 * len(DESIGNS)} figures")

    if args.pr_body:
        prefix = args.pr_body if args.pr_body.endswith("/") else args.pr_body + "/"
        # ?raw=true: a bare blob URL renders GitHub's HTML page for the
        # file, not the image itself, so the PR body would show a link
        # where the figure should be.
        body = render(
            data,
            gt_runtimes,
            path_counts,
            image_prefix=prefix,
            image_suffix="?raw=true",
            directory=directory,
        )
        with open(os.path.join(directory, "README.pr.md"), "w") as f:
            f.write(body + "\n")
        print("Wrote README.pr.md")


if __name__ == "__main__":
    main()
