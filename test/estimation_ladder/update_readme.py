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
    # Same design, same estimator runs, scored only on the paths that
    # touch a macro pin -- a separate population, and a separate
    # question: what does it take to estimate macro timing?
    ("multiplier_top_macro", "multiplier_top, macro paths only"),
]

# Which error each study is built against.
ACCURACY_KEY = {
    "multiplier": "mean_rel_err",
    "multiplier_top": "mean_rel_err",
    "multiplier_top_macro": "mean_rel_err_macro",
}


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

# Only present on a design that has macros, and worth its own columns
# there: averaging the two populations together hid the fact that the
# estimator orders the macro paths backwards.
MACRO_COLUMNS = [
    "mean_rel_err_nonmacro",
    "kendall_tau_nonmacro",
    "mean_rel_err_macro",
    "kendall_tau_macro",
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


def ground_truth_stages(path):
    """The flow's own stages. "The flow takes 668s" says nothing about
    what the estimator is declining to run, and it turns out over half of
    it is a single stage."""
    if not os.path.exists(path):
        return {}
    raw = json.load(open(path)).get("stages", {})
    # 2_floorplan -> floorplan, 5_1_grt -> global_route, and so on.
    # Onto the estimator's own phase names, so the same work is the same
    # colour on both bars and the two are actually comparable.
    rename = {
        "floorplan": "floorplan",
        "floorplan_pdn": "floorplan",
        "floorplan_tapcell": "floorplan",
        "floorplan_macro": "macro_place",
        "place_iop": "place_pins",
        "place_gp_skip_io": "global_place",
        "place_gp": "global_place",
        "place_resized": "repair_design",
        "place_dp": "detailed_place",
        "cts": "cts",
        "grt": "global_route",
        "route": "global_route",
    }
    out = {}
    for k, v in raw.items():
        tail = k.split("_", 1)[-1].lstrip("0123456789_")
        name = rename.get(tail, tail)
        out[name] = out.get(name, 0.0) + v
    return out


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
    key = ACCURACY_KEY.get(design, "mean_rel_err")
    fig, ax = plt.subplots(figsize=(10, 6))
    if front:
        ax.scatter(
            [m["runtime_s"] for m in front["measured"] if key in m],
            [m[key] for m in front["measured"] if key in m],
            s=22,
            color="0.72",
            label="measured",
        )
        pts = [
            p for p in sorted(front["front"], key=lambda p: p["runtime_s"]) if key in p
        ]
        ax.plot(
            [p["runtime_s"] for p in pts],
            [p[key] for p in pts],
            "o-",
            color="tab:blue",
            label="Pareto front (numbered as in the table)",
        )
        _annotate_numbered(ax, pts, key)
    _ground_truth_line(ax, gt)
    ax.set_xscale("log")
    ax.set_xlabel("runtime (s, log scale)")
    ax.set_ylabel(
        "mean relative error"
        + (" (macro paths only)" if key.endswith("_macro") else "")
    )
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
    pts = sorted(front["front"], key=lambda p: p["runtime_s"])
    has_macro = any("mean_rel_err_macro" in p for p in pts)
    cols = FRONT_COLUMNS + (MACRO_COLUMNS if has_macro else [])
    rows = []
    for n, p in enumerate(pts, 1):
        row = {"#": n, "rungs": rung_label(p["env"])}
        row.update({c: p.get(c) for c in cols})
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


# Phases in the order they run, so a stacked bar reads left to right as
# the rung actually executes.
PHASE_ORDER = [
    "load",
    "floorplan",
    "place_pins",
    "macro_place",
    "global_place",
    "cts",
    "repair_design",
    "global_route",
    "detailed_place",
    "repair_timing",
    "sta",
]
PHASE_COLORS = {
    # load and sta are deliberately the two greys: they are the overhead
    # every rung pays regardless of what it runs.  Nothing else should be
    # grey, or the distinction stops carrying meaning.
    "load": "0.78",
    "floorplan": "tab:purple",
    "place_pins": "tab:olive",
    "macro_place": "tab:orange",
    "global_place": "tab:blue",
    "cts": "tab:green",
    "repair_design": "tab:cyan",
    "global_route": "tab:red",
    "detailed_place": "tab:pink",
    "repair_timing": "tab:brown",
    "sta": "0.45",
}
# Overhead you pay to get any timing number at all, whatever the rung.
FIXED_PHASES = {"load", "sta"}


def plot_time_breakdown(directory, design, title, front, flow_stages):
    """Where the seconds go, on both sides of the comparison.

    A speedup ratio is a conclusion; this is the thing the conclusion
    comes from.  The flow's own stages sit on the same axis as the rungs,
    so it is visible at a glance that the estimator is not skipping
    routing so much as running a far cheaper version of it, and that the
    cheapest rungs are almost entirely fixed overhead.
    """
    if not front or not front["front"]:
        return
    pts = sorted(front["front"], key=lambda p: p["runtime_s"])
    labels, stacks = [], []

    if flow_stages:
        labels.append("the full flow")
        stacks.append(dict(flow_stages))

    for n, p in enumerate(pts, 1):
        labels.append(f"{n}. {rung_label(p['env'])}")
        stacks.append(dict(p.get("phases", {})))

    keys = [k for k in PHASE_ORDER if any(k in st for st in stacks)]
    extra = sorted({k for st in stacks for k in st} - set(PHASE_ORDER))
    keys += extra

    totals = [sum(st.values()) or 1.0 for st in stacks]
    fig, ax = plt.subplots(figsize=(11, 1.2 + 0.55 * len(labels)))
    ypos = range(len(labels))
    left = [0.0] * len(labels)
    for k in keys:
        vals = [100.0 * st.get(k, 0.0) / t for st, t in zip(stacks, totals)]
        ax.barh(
            list(ypos),
            vals,
            left=left,
            label=k,
            color=PHASE_COLORS.get(k, "tab:purple"),
            edgecolor="white",
            height=0.7,
        )
        left = [a + b for a, b in zip(left, vals)]
    for y, total in zip(ypos, totals):
        ax.text(101, y, f"{total:.3g}s", va="center", fontsize=9, fontweight="bold")
    ax.set_yticks(list(ypos))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xlabel("share of that row's runtime (%) -- absolute total at right")
    ax.set_title(f"{title}: where the time goes")
    ax.legend(fontsize=8, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(os.path.join(directory, f"time_{design}.png"), dpi=120)
    plt.close(fig)


def breakdown_table(front, flow_stages, flow_total):
    """Fixed overhead against estimation work, per rung.

    The split that makes the cheap rungs honest: loading the design and
    running the timing query cost the same whatever the rung does, so a
    rung that runs almost no flow stages is nearly all overhead, and its
    speedup is a property of these designs being small rather than of the
    method.
    """
    if not front or not front["front"]:
        return []
    rows = []
    if flow_stages:
        rows.append(
            {
                "rung": "the full flow (baseline)",
                "total_s": flow_total,
                "overhead_s": None,
                "work_s": flow_total,
                "overhead_pct": None,
                "vs flow": "1x",
            }
        )
    prev = None
    for n, p in enumerate(sorted(front["front"], key=lambda p: p["runtime_s"]), 1):
        ph = p.get("phases", {})
        fixed = sum(v for k, v in ph.items() if k in FIXED_PHASES)
        total = p["runtime_s"]
        rows.append(
            {
                "rung": f"{n}. {rung_label(p['env'])}",
                "total_s": total,
                "overhead_s": fixed,
                "work_s": max(total - fixed, 0.0),
                "overhead_pct": (100.0 * fixed / total) if total else None,
                "vs flow": f"{flow_total / total:.0f}x" if flow_total else "",
            }
        )
        prev = p
    return rows


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
        "### What a runtime includes",
        "",
        "Everything from having the post-synthesis netlist to having a timing",
        "number: reading the ODB, the SDC and the liberties, whatever flow",
        "stages the rung runs, and the timing queries themselves. OpenSTA",
        "builds its graph and computes delays on the first query, so the query",
        "is not bookkeeping around the result -- on a rung that runs no flow",
        "stages it is most of the work. An earlier version of this study timed",
        "only the flow stages, which reported a rung whose real cost is 3.5s at",
        "0.024s and made it look thousands of times faster than the flow rather",
        "than a couple of hundred.",
        "",
        "The flow baseline is summed from its own stage logs, each of which",
        "includes that stage's load, so both sides are counted the same way.",
        "",
        "Load and timing-query cost scale with design size. On a design much",
        "larger than these the fixed overhead grows, and the cheapest rungs",
        "lose most of their apparent advantage; the rungs that run real flow",
        "stages are affected proportionally less.",
        "",
        "### How these times would scale",
        "",
        "Not measured -- there is no large design here -- but the components",
        "scale differently and it is worth knowing which way. Loading grows",
        "with netlist size. The timing query grows with the number of paths",
        "and their depth. Global placement grows faster than linearly in",
        "instance count. Global routing grows with net count and, badly, with",
        "congestion. The fixed overhead therefore grows more slowly than the",
        "flow does, so the rungs that run real stages should hold their",
        "advantage on a larger design while the near-empty rungs lose most of",
        "theirs.",
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


def headline(data, gt_runtimes):  # noqa: C901
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
        # Each study is scored against its own error: the macro study on
        # the paths that touch a macro pin, the others on all of them.
        key = ACCURACY_KEY.get(design, "mean_rel_err")
        placed = [
            p
            for p in front["front"]
            if str(p["env"].get("RUN_PLACE", "0")) == "1" and key in p
        ]
        if not placed:
            continue
        # The rung someone would actually choose: the cheapest one within
        # a percentage point of the best accuracy on offer, rather than
        # the most accurate at any price.
        best_err = min(p[key] for p in placed)
        pick = min(
            (p for p in placed if p[key] <= best_err + 0.01),
            key=lambda p: p["runtime_s"],
        )
        ph = pick.get("phases", {})
        fixed = sum(v for k, v in ph.items() if k in FIXED_PHASES)
        detail = ""
        if fixed:
            detail = (
                f", of which {fixed:.3g}s is loading the design and running "
                f"the timing query -- overhead any rung pays"
            )
        out.append(
            f"- **{title}**: the flow takes **{gt:.0f}s**. The estimator gets "
            f"within **{pick[key]:.1%}** of it in "
            f"**{pick['runtime_s']:.3g}s**{detail}."
        )
    return out


def render(
    data,
    gt_runtimes,
    path_counts,
    image_prefix="",
    image_suffix="",
    directory=".",
    flow_stages=None,
):
    flow_stages = flow_stages or {}
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
        "The synthesis-only rung is in the tables below as an accuracy",
        "floor -- what you get for reading the netlist and asking OpenSTA --",
        "not as a speedup to quote. Almost all of its runtime is loading the",
        "design and running the timing query, and both of those grow with",
        "design size while the flow grows faster still. Read its ratio as an",
        "artifact of these designs being small, not as something that would",
        "hold on a real one.",
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
        stages = flow_stages.get(design, {})
        if stages:
            ordered = sorted(stages.items(), key=lambda kv: -kv[1])
            total = sum(stages.values()) or 1.0
            name, cost = ordered[0]
            share = 100.0 * cost / total
            out += [
                "**Where the flow's time goes**, largest first: "
                + ", ".join(f"{k} {v:.0f}s" for k, v in ordered)
                + f". The single biggest stage is {name} at {share:.0f}% of the "
                f"flow, and the estimator does not skip it so much as run a far "
                f"cheaper version of it -- which is where the saving comes from.",
                "",
            ]
        # What each stage adds, taken from the rung that runs the most of
        # them: this is how someone decides what to switch on, and it is
        # where repair_timing costing more than CTS and global routing
        # together becomes obvious.
        deepest = None
        if front and front["front"]:
            deepest = max(front["front"], key=lambda p: len(p.get("phases", {})))
        if deepest and len(deepest.get("phases", {})) > 3:
            costs = ", ".join(
                f"{k} {v:.3g}s"
                for k, v in sorted(deepest["phases"].items(), key=lambda kv: -kv[1])
                if k not in FIXED_PHASES
            )
            out += [
                f"**What each stage costs**, from the deepest rung measured "
                f"({rung_label(deepest['env'])}): {costs}.",
                "",
            ]

        # The split that the aggregate was hiding.
        pts = sorted(front["front"], key=lambda p: p["runtime_s"]) if front else []
        macro_pts = [p for p in pts if "kendall_tau_macro" in p]
        if macro_pts:
            worst = min(macro_pts, key=lambda p: p["kendall_tau_macro"])
            best = max(macro_pts, key=lambda p: p["kendall_tau_macro"])
            n_m = worst.get("n_macro")
            n_n = worst.get("n_nonmacro")
            out += [
                f"**Macro paths behave differently, and worse.** Of the "
                f"{(n_m or 0) + (n_n or 0)} sampled paths, {n_m} touch a macro "
                f"pin and {n_n} do not, and the two are separate populations: "
                f"the macro paths run faster and none of them is among the ten "
                f"worst overall, which is why a slack-ranked sample reaches "
                f"almost none of them and has to be told to go and find them. "
                f"Scored on their own, rank correlation across the front runs "
                f"from {worst['kendall_tau_macro']:+.2f} to "
                f"{best['kendall_tau_macro']:+.2f} against "
                f"{worst['kendall_tau_nonmacro']:+.2f} to "
                f"{best['kendall_tau_nonmacro']:+.2f} on everything else. Where "
                f"that number is negative the estimator is ordering the macro "
                f"paths backwards, and the healthy-looking aggregate is the "
                f"non-macro majority outvoting them.",
                "",
            ]

        rows = breakdown_table(front, stages, gt)
        if rows:
            out += [
                "**Where each rung's time goes.** Overhead is loading the design "
                "and running the timing query, which cost the same whatever the "
                "rung does.",
                "",
                pd.DataFrame(rows).to_markdown(index=False, floatfmt=".3g"),
                "",
                f"![{title} time breakdown]({image_prefix}time_{design}.png{image_suffix})",
                "",
            ]
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

    # The macro study is the same design and the same flow, scored on a
    # subset of the paths, so it shares multiplier_top's baseline and
    # stage breakdown. Its chance level, though, is set by how many macro
    # paths there are, not by the full sample.
    gt_runtimes["multiplier_top_macro"] = gt_runtimes.get("multiplier_top")

    # How many paths were sampled sets the chance baseline for recall@10.
    path_counts = {}
    for design, gt_path in (
        ("multiplier", args.ground_truth_json),
        ("multiplier_top", args.ground_truth_top_json),
    ):
        if os.path.exists(gt_path):
            path_counts[design] = len(json.load(open(gt_path))["paths"])

    flow_stages = {
        "multiplier": ground_truth_stages(args.ground_truth_json),
        "multiplier_top": ground_truth_stages(args.ground_truth_top_json),
    }

    macro_front = data.get("multiplier_top_macro", (None, None))[0]
    if macro_front and macro_front["front"]:
        n_macro = macro_front["front"][0].get("n_macro")
        if n_macro:
            path_counts["multiplier_top_macro"] = n_macro
    flow_stages["multiplier_top_macro"] = flow_stages.get("multiplier_top", {})

    for design, title in DESIGNS:
        front, _ = data[design]
        plot_time_breakdown(
            directory, design, title, front, flow_stages.get(design, {})
        )
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

    readme = render(
        data, gt_runtimes, path_counts, directory=directory, flow_stages=flow_stages
    )
    with open(os.path.join(directory, "README.md"), "w") as f:
        f.write(readme + "\n")
    print(f"Wrote README.md and {4 * len(DESIGNS)} figures")

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
            flow_stages=flow_stages,
            image_suffix="?raw=true",
            directory=directory,
        )
        with open(os.path.join(directory, "README.pr.md"), "w") as f:
            f.write(body + "\n")
        print("Wrote README.pr.md")


if __name__ == "__main__":
    main()
