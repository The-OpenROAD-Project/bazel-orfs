#!/usr/bin/env python3
"""Generate a Gantt chart of bazel-orfs development activities.

Reads git --numstat history and classifies commits by actual files
changed into activity groups.

Usage:
    python docs/generate_gantt.py -o docs/gantt.png

LLM UPDATE INSTRUCTIONS:
    When asked to update the Gantt chart:
    1. Read recent git history to check for new feature areas:
       git log --numstat --format="%ad %s" --date=short | head -100
    2. If new directories or .bzl files appeared that don't match any
       file_patterns in ACTIVITIES below, add a new activity entry.
    3. If features were retired (files deleted), move them to the
       Retired group.
    4. Regenerate: python docs/generate_gantt.py -o docs/gantt.png
    5. Commit generate_gantt.py and gantt.png together.
"""

import argparse
import re
import subprocess
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches

# Color per group
GROUP_COLORS = {
    "Core Rules": "#2196F3",
    "Features": "#4CAF50",
    "Verification": "#FF9800",
    "Toolchains": "#9C27B0",
    "Infrastructure": "#607D8B",
    "Project": "#795548",
    "Retired": "#E0E0E0",
}

# Each activity: (name, group, file_patterns, exclude_patterns)
# file_patterns are Python regexes matched against paths from git --numstat.
# A commit counts toward an activity if it touched matching files.
ACTIVITIES = [
    # --- Core Rules ---
    ("Core rules (openroad.bzl)", "Core Rules", [r"^openroad\.bzl$"], [r"\.lock$"]),
    (
        "Deploy & local flow",
        "Core Rules",
        [r"deploy\.tpl$", r"make\.tpl$", r"make_script"],
        [],
    ),
    (
        "Variable metadata",
        "Core Rules",
        [r"load_json_file\.bzl$", r"config\.bzl$", r"extension\.bzl$"],
        [],
    ),
    # --- Features ---
    ("Mock area & abstracts", "Features", [r"mock_area", r"abstract"], []),
    (
        "Sweep & DSE",
        "Features",
        [r"sweep\.bzl$", r"sweep.*\.tcl$", r"sweep.*\.py$"],
        [],
    ),
    ("PPA analysis", "Features", [r"ppa\.bzl$"], []),
    ("SRAM support", "Features", [r"sram/"], []),
    ("Naja post-synthesis", "Features", [r"naja/"], []),
    ("orfs_genrule", "Features", [r"orfs_genrule\.bzl$"], []),
    # --- Verification ---
    ("EQY equivalence checking", "Verification", [r"eqy[\.-]", r"eqy\.bzl$"], []),
    (
        "SBY formal verification",
        "Verification",
        [r"sby[\./]", r"sby\.bzl$", r"sby\.tpl$"],
        [],
    ),
    # --- Toolchains ---
    (
        "Chisel & Scala",
        "Toolchains",
        [r"chisel/", r"generate\.bzl$", r"bloop", r"\.scala$"],
        [],
    ),
    (
        "Verilog & Yosys",
        "Toolchains",
        [r"verilog\.bzl$", r"yosys\.bzl$", r"slang/"],
        [],
    ),
    ("Verilator", "Toolchains", [r"verilator"], []),
    # --- Infrastructure ---
    (
        "Docker image extraction",
        "Infrastructure",
        [r"docker\.bzl$", r"docker\.BUILD", r"docker_shell", r"patcher\.py$"],
        [],
    ),
    ("PDK support", "Infrastructure", [r"asap7/", r"sky130", r"ihp"], []),
    (
        "Bazel module & deps",
        "Infrastructure",
        [r"MODULE\.bazel$", r"WORKSPACE$", r"\.bazelversion$", r"requirements.*\.txt$"],
        [r"\.lock$"],
    ),
    ("CI & GitHub Actions", "Infrastructure", [r"\.github/", r"\.bazelrc$"], []),
    (
        "Pin artifacts",
        "Infrastructure",
        [r"pin\.bzl$", r"tools/pin/", r"extensions/pin"],
        [],
    ),
    ("Documentation", "Project", [r"README\.md$", r"docs/"], []),
    # --- Retired ---
    ("Docker shell (retired)", "Retired", [r"docker_shell"], []),
    (
        "netlistsvg (retired)",
        "Retired",
        [r"netlistsvg", r"pnpm", r"rules_js", r"main\.js$"],
        [],
    ),
]


def get_git_numstat():
    """Get git log with --numstat."""
    result = subprocess.run(
        ["git", "log", "--numstat", "--format=COMMIT\t%ad\t%s", "--date=short"],
        capture_output=True,
        text=True,
        check=True,
    )
    commits = []
    current = None
    for line in result.stdout.split("\n"):
        if line.startswith("COMMIT\t"):
            parts = line.split("\t", 2)
            if len(parts) >= 3:
                if current:
                    commits.append(current)
                current = {
                    "date": datetime.strptime(parts[1], "%Y-%m-%d"),
                    "subject": parts[2],
                    "files": [],
                }
        elif line.strip() and current is not None:
            parts = line.split("\t")
            if len(parts) >= 3:
                added = int(parts[0]) if parts[0] != "-" else 0
                removed = int(parts[1]) if parts[1] != "-" else 0
                filepath = parts[2]
                if " => " in filepath:
                    filepath = filepath.split(" => ")[-1]
                current["files"].append((filepath, added + removed))
    if current:
        commits.append(current)
    return commits


def classify_and_span(commits):
    """Classify commits and compute time spans per activity.

    Returns {name: (segments, total_loc, commit_count)}
    where segments is [(start, end, loc), ...]
    """
    gap_threshold = timedelta(days=45)
    spans = {}

    for name, _group, patterns, excludes in ACTIVITIES:
        date_locs = []
        for commit in commits:
            loc = 0
            for filepath, lines_changed in commit["files"]:
                if any(re.search(e, filepath) for e in excludes):
                    continue
                if any(re.search(p, filepath) for p in patterns):
                    loc += lines_changed
            if loc > 0:
                date_locs.append((commit["date"], loc))

        if not date_locs:
            continue

        sorted_entries = sorted(date_locs, key=lambda x: x[0])
        total_loc = sum(loc for _, loc in sorted_entries)

        # Merge into segments
        segments = []
        seg_start = sorted_entries[0][0]
        seg_end = sorted_entries[0][0]
        seg_loc = sorted_entries[0][1]

        for date, loc in sorted_entries[1:]:
            if date - seg_end <= gap_threshold:
                seg_end = date
                seg_loc += loc
            else:
                segments.append((seg_start, seg_end, seg_loc))
                seg_start = date
                seg_end = date
                seg_loc = loc
        segments.append((seg_start, seg_end, seg_loc))

        # Minimum 7-day visual width
        segments = [(s, max(e, s + timedelta(days=7)), loc) for s, e, loc in segments]
        spans[name] = (segments, total_loc, len(sorted_entries))

    return spans


def render_gantt(spans, commits, output_file=None):
    activity_order = [
        (name, group) for name, group, _, _ in ACTIVITIES if name in spans
    ]

    if not activity_order:
        print("No matching commits found.")
        return

    fig, ax = plt.subplots(figsize=(18, 11))
    fig.subplots_adjust(left=0.22, right=0.88, top=0.92, bottom=0.10)

    # Max segment LOC for alpha scaling
    all_seg_locs = []
    for name, _ in activity_order:
        segs, _, _ = spans[name]
        all_seg_locs.extend(loc for _, _, loc in segs)
    max_seg_loc = max(all_seg_locs) if all_seg_locs else 1

    y_labels = []
    y_positions = []
    current_group = None
    y = 0
    group_y_ranges = {}

    for name, group in reversed(activity_order):
        if group != current_group:
            if current_group is not None:
                y += 0.4
            group_y_ranges.setdefault(group, [y, y])
            current_group = group

        segments, total_loc, commit_count = spans[name]
        color = GROUP_COLORS.get(group, "#999999")

        for seg_start, seg_end, seg_loc in segments:
            duration = (seg_end - seg_start).days
            alpha = 0.35 + 0.65 * min(1.0, seg_loc / (max_seg_loc * 0.3))
            ax.barh(
                y,
                duration,
                left=mdates.date2num(seg_start),
                height=0.6,
                color=color,
                alpha=alpha,
                edgecolor="white",
                linewidth=0.5,
            )

        last_end = max(e for _, e, _ in segments)
        loc_str = f"{total_loc:,}" if total_loc >= 1000 else str(total_loc)
        ax.text(
            mdates.date2num(last_end) + 5,
            y,
            f"{loc_str} LOC  ({commit_count})",
            va="center",
            ha="left",
            fontsize=7,
            color="#555555",
        )

        y_labels.append(name)
        y_positions.append(y)
        group_y_ranges[group][1] = y
        y += 1

    ax.set_yticks(y_positions)
    ax.set_yticklabels(y_labels, fontsize=9)

    for group, (y_min, y_max) in group_y_ranges.items():
        mid = (y_min + y_max) / 2
        color = GROUP_COLORS.get(group, "#999999")
        ax.text(
            1.01,
            mid,
            group,
            transform=ax.get_yaxis_transform(),
            va="center",
            ha="left",
            fontsize=8,
            fontweight="bold",
            color=color,
        )

    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.xticks(rotation=45, ha="right", fontsize=8)

    ax.grid(axis="x", alpha=0.3, linestyle="--")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.set_title(
        "bazel-orfs Development Timeline" " (by files changed)",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel("Date", fontsize=10)

    legend_patches = [mpatches.Patch(color=c, label=g) for g, c in GROUP_COLORS.items()]
    legend_patches.append(
        mpatches.Patch(
            facecolor="#999999",
            alpha=0.35,
            label="Low intensity",
        )
    )
    legend_patches.append(
        mpatches.Patch(
            facecolor="#999999",
            alpha=1.0,
            label="High intensity",
        )
    )
    ax.legend(
        handles=legend_patches,
        loc="upper left",
        fontsize=8,
        framealpha=0.9,
        ncol=2,
    )

    all_dates = [c["date"] for c in commits]
    date_min, date_max = min(all_dates), max(all_dates)
    total_loc = sum(loc for _, loc, _ in spans.values())
    ax.text(
        0.99,
        0.01,
        f"{len(commits)} commits | {total_loc:,} LOC | "
        f"{date_min:%b %Y} \u2013 {date_max:%b %Y}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#999999",
    )

    if output_file:
        fig.savefig(output_file, dpi=150, bbox_inches="tight")
        print(f"Saved to {output_file}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Generate bazel-orfs development " "Gantt chart"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file (e.g. docs/gantt.png)",
    )
    args = parser.parse_args()

    commits = get_git_numstat()
    print(f"Scanned {len(commits)} commits")
    spans = classify_and_span(commits)
    render_gantt(spans, commits, args.output)


if __name__ == "__main__":
    main()
