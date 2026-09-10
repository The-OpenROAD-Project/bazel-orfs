#!/usr/bin/env python3
"""Generate the study's tables from whatever the campaign has recorded.

The pull request body is the report, and every table in it comes from
here so that a re-run cannot leave a hand-typed number behind. Results
are discovered, not declared: a new design or arm appears by being run,
and a section with nothing to show says so rather than rendering as if
it had been measured.

    bazelisk run //test/repair_timing_runtime:report -- [--results DIR]

Two statistics, both from the threads study: spread is 2σ of the
repeats (zero for a single run, which is honest), and the resolvable
difference between two arms with k repeats each is 2σ·sqrt(2/k). A
difference inside that is "did not resolve", which is not "no effect".
"""

import argparse
import glob
import json
import math
import os
import statistics
import sys

# ORFS call sites, in flow order, and their column names.
KINDS = [
    ("repair_design", "repair_design"),
    ("setup_hold", "setup+hold"),
    ("floorplan_setup", "floorplan setup"),
    ("post_grt_wns", "post-grt WNS"),
]


def load_results(results_dir):
    """Every result JSON under results_dir, or SystemExit if there are none."""
    paths = sorted(glob.glob(os.path.join(results_dir, "*.json")))
    if not paths:
        raise SystemExit(
            "no results directory at {}: run the campaign first".format(results_dir)
        )
    records = []
    for path in paths:
        with open(path) as handle:
            records.append(json.load(handle))
    return records


def two_sigma(values):
    return 2.0 * statistics.pstdev(values) if len(values) > 1 else 0.0


def resolution(sigma2, k):
    return sigma2 * math.sqrt(2.0 / max(k, 1))


def fmt(value, digits=1, unit=""):
    if value is None:
        return "–"
    if isinstance(value, float):
        return "{:.{d}f}{u}".format(value, d=digits, u=unit)
    return "{}{}".format(value, unit)


def repair_calls(record):
    """(substep, call summary, substep wall) for every repair call recorded."""
    out = []
    for step, got in sorted(record["substeps"].items()):
        for call in got.get("repair", []):
            out.append((step, call, got.get("wall_s")))
    return out


def dead_share(call):
    """Share of the main-phase grind after the last improvement.

    By elapsed stamps when the log was stamped, by iteration count
    otherwise. None when the call printed no trajectory.
    """
    if call.get("final_iter") is None:
        return None
    if call.get("t_final_s") and call.get("t_last_improvement_s") is not None:
        # Rows carry absolute stamps; the call's own start is its echo.
        start = call.get("start_s") or 0
        total = call["t_final_s"] - start
        if total > 0:
            return (call["t_final_s"] - call["t_last_improvement_s"]) / total
    if call["final_iter"]:
        return (call["final_iter"] - call["last_improving_iter"]) / call["final_iter"]
    return None


def census_rows(records, arm="base"):
    """One row per (design, stage, call) for the census arm, first repeat."""
    rows = []
    seen = set()
    for record in sorted(records, key=lambda r: (r["design"], r["stage"], r["repeat"])):
        if record["arm"] != arm:
            continue
        key = (record["design"], record["stage"])
        if key in seen:
            continue
        seen.add(key)
        for step, call, wall in repair_calls(record):
            seconds = (
                call.get("repair_design_s")
                if call["kind"] == "repair_design"
                else (call.get("setup_s") or 0) + (call.get("hold_s") or 0)
            )
            rows.append(
                {
                    "design": record["design"],
                    "stage": record["stage"],
                    "substep": step,
                    "kind": call["kind"],
                    "seconds": seconds,
                    "setup_s": call.get("setup_s"),
                    "hold_s": call.get("hold_s"),
                    "wall_s": wall,
                    "share": (seconds / wall) if (wall and seconds) else None,
                    "iterations": call.get("iterations"),
                    "dead_share": dead_share(call),
                    "endpoints": call.get("endpoints"),
                    "wns_start": call.get("wns_start"),
                    "wns_end": call.get("wns_end"),
                    "unrepaired": call.get("unrepaired"),
                }
            )
    return rows


def census_table(rows):
    """The census: where repair_timing's seconds are, design by call site."""
    if not rows:
        return "Not yet measured.\n"
    lines = [
        "| design | stage | call | seconds | of substep | iterations | grind after last gain | WNS start → end (ps) | endpoints |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for r in rows:
        wns = (
            "{} → {}".format(fmt(r["wns_start"]), fmt(r["wns_end"]))
            if r["wns_start"] is not None
            else "–"
        )
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r["design"],
                r["stage"],
                dict(KINDS).get(r["kind"], r["kind"]),
                fmt(r["seconds"]),
                fmt(r["share"] * 100, 0, "%") if r["share"] is not None else "–",
                fmt(r["iterations"]) if r["iterations"] else "–",
                fmt(r["dead_share"] * 100, 0, "%") if r["dead_share"] is not None else "–",
                wns,
                fmt(r["endpoints"]),
            )
        )
    return "\n".join(lines) + "\n"


def stage_share_table(records, arm="base"):
    """Per design: stage wall vs the seconds inside repair_timing."""
    rows = census_rows(records, arm)
    if not rows:
        return "Not yet measured.\n"
    per = {}
    for r in rows:
        key = (r["design"], r["stage"])
        entry = per.setdefault(key, {"wall": r["wall_s"] or 0, "repair": 0.0})
        if r["kind"] != "repair_design" and r["seconds"]:
            entry["repair"] += r["seconds"]
    lines = [
        "| design | stage | substep wall (s) | in repair_timing (s) | share |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for (design, stage), entry in sorted(per.items()):
        share = entry["repair"] / entry["wall"] if entry["wall"] else None
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                design, stage, fmt(entry["wall"], 0), fmt(entry["repair"], 0),
                fmt(share * 100, 0, "%") if share is not None else "–",
            )
        )
    return "\n".join(lines) + "\n"


def arm_samples(records, design, stage, kind="setup_hold"):
    """arm -> list of (seconds, wns_end, sha1) over repeats, for one call kind."""
    out = {}
    for record in records:
        if record["design"] != design or record["stage"] != stage:
            continue
        for step, call, _ in repair_calls(record):
            if call["kind"] != kind:
                continue
            seconds = (call.get("setup_s") or 0) + (call.get("hold_s") or 0)
            sha = record["substeps"][step].get("result_sha1")
            out.setdefault(record["arm"], []).append((seconds, call.get("wns_end"), sha))
    return out


def arms_table(records, design, stage, base="base"):
    """Every arm against the base for one (design, stage)."""
    samples = arm_samples(records, design, stage)
    if base not in samples or len(samples) < 2:
        return "Not yet measured.\n"
    base_secs = [s for s, _, _ in samples[base]]
    base_med = statistics.median(base_secs)
    sigma2 = two_sigma(base_secs)
    base_wns = statistics.median([w for _, w, _ in samples[base] if w is not None] or [0])
    base_sha = {sha for _, _, sha in samples[base]}
    lines = [
        "| arm | setup+hold (s), each repeat | median | delta | 2σ (base) | resolution | verdict | WNS end delta (ps) | same ODB as base |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for arm in sorted(samples, key=lambda a: (a != base, a)):
        secs = [s for s, _, _ in samples[arm]]
        med = statistics.median(secs)
        delta = med - base_med
        res = resolution(sigma2, min(len(secs), len(base_secs)))
        if arm == base:
            verdict = "control"
        elif abs(delta) <= res:
            verdict = "did not resolve"
        else:
            verdict = "faster" if delta < 0 else "slower"
        wns = [w for _, w, _ in samples[arm] if w is not None]
        wns_delta = statistics.median(wns) - base_wns if wns else None
        shas = {sha for _, _, sha in samples[arm]}
        same = "yes" if shas and shas == base_sha else ("no" if shas else "–")
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                arm,
                ", ".join(fmt(s) for s in secs),
                fmt(med),
                fmt(delta, 1, "") if arm != base else "–",
                fmt(sigma2),
                fmt(res),
                verdict,
                fmt(wns_delta, 1) if wns_delta is not None else "–",
                same,
            )
        )
    return "\n".join(lines) + "\n"


# Profile fields, in the order the attribution table shows them. sta_s
# encloses worst_s and repair_path_s encloses generate_s and commit_s,
# so the table shows the enclosing ones and lists the inner as detail.
PROFILE_COLUMNS = [
    ("sta_s", "STA"),
    ("progress_s", "progress row"),
    ("journal_s", "journal"),
    ("path_s", "path lookup"),
    ("begin_s", "endpoint begin"),
    ("repair_path_s", "repair work"),
    ("parasitics_s", "parasitics"),
    ("collect_s", "collect"),
    ("tns_s", "tns check"),
]


def attribution_rows(records, arm_prefix="base"):
    """Per (design, stage, call): where the profiled binary says the seconds went.

    Uses the last phase's cumulative profile line of the setup+hold and
    floorplan calls from arms whose name starts with `arm_prefix` (the
    profiled base carries a suffix). One row per (design, stage, call),
    first repeat.
    """
    rows = []
    seen = set()
    for record in sorted(records, key=lambda r: (r["design"], r["stage"], r["repeat"])):
        if not record["arm"].startswith(arm_prefix):
            continue
        for step, call, wall in repair_calls(record):
            if not call.get("profile") or call["kind"] == "repair_design":
                continue
            key = (record["design"], record["stage"], call["kind"])
            if key in seen:
                continue
            seen.add(key)
            prof = list(call["profile"].values())[-1]
            total = call.get("setup_s") or 0
            accounted = sum(prof.get(k, 0) for k, _ in PROFILE_COLUMNS)
            phase = prof.get("phase_s")
            rows.append(
                {
                    "design": record["design"],
                    "stage": record["stage"],
                    "kind": call["kind"],
                    "setup_s": total,
                    "passes": prof.get("passes"),
                    "profile": prof,
                    "other_s": max((phase if phase else total) - accounted, 0.0),
                    "outside_s": max(total - phase, 0.0) if phase else None,
                    "arm": record["arm"],
                }
            )
    return rows


def attribution_table(rows):
    if not rows:
        return "Not yet measured.\n"
    lines = [
        "| design | stage | call | setup (s) | passes | "
        + " | ".join(label for _, label in PROFILE_COLUMNS)
        + " | other in phase | outside phases | accepted / attempts |",
        "| --- | --- | --- | ---: | ---: | " + " | ".join("---:" for _ in PROFILE_COLUMNS) + " | ---: | ---: | ---: |",
    ]
    for r in rows:
        p = r["profile"]
        cells = []
        for key, _ in PROFILE_COLUMNS:
            v = p.get(key)
            share = (100.0 * v / r["setup_s"]) if (v is not None and r["setup_s"]) else None
            cells.append("{} ({})".format(fmt(v), fmt(share, 0, "%")) if v is not None else "–")
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} / {} |".format(
                r["design"], r["stage"], dict(KINDS).get(r["kind"], r["kind"]),
                fmt(r["setup_s"]), fmt(r["passes"]), " | ".join(cells),
                fmt(r["other_s"]), fmt(r["outside_s"]),
                fmt(p.get("accepted")), fmt(p.get("attempts")),
            )
        )
    return "\n".join(lines) + "\n"


def trajectory_chart(record, step, call_index=0, title=None):
    """A mermaid xychart of WNS against elapsed seconds for one call.

    Renders in a GitHub PR body with no committed asset. Falls back to
    iterations on the x axis when the log was not stamped.
    """
    rows = record["substeps"][step]["repair_rows"][call_index]
    main = [r for r in rows if r["iter"] != "final" and r["marker"] == "*"]
    if not main:
        return ""
    stamped = all(r["t_s"] is not None for r in main)
    xs = [r["t_s"] - main[0]["t_s"] for r in main] if stamped else [r["iter"] for r in main]
    ys = [r["wns"] for r in main]
    # xychart wants categorical x labels; thin to at most 40 points.
    stride = max(1, len(xs) // 40)
    xs, ys = xs[::stride], ys[::stride]
    return (
        "```mermaid\n"
        "xychart-beta\n"
        '    title "{}"\n'
        '    x-axis "{}" [{}]\n'
        '    y-axis "WNS (ps)"\n'
        "    line [{}]\n"
        "```\n"
    ).format(
        title or "{} {} repair_timing".format(record["design"], step),
        "elapsed s" if stamped else "iteration",
        ", ".join("{:.0f}".format(x) for x in xs),
        ", ".join("{:.1f}".format(y) for y in ys),
    )


def render(records):
    parts = ["## Census: where repair_timing's seconds are\n", census_table(census_rows(records))]
    parts += ["\n## Share of the stage\n", stage_share_table(records)]
    parts += ["\n## Attribution: where a pass spends its seconds\n",
              attribution_table(attribution_rows(records))]
    pairs = sorted({(r["design"], r["stage"]) for r in records})
    parts.append("\n## Arms\n")
    any_arm = False
    for design, stage in pairs:
        table = arms_table(records, design, stage)
        if table.startswith("Not yet"):
            continue
        any_arm = True
        parts.append("\n### {} {}\n\n".format(design, stage))
        parts.append(table)
    if not any_arm:
        parts.append("Not yet measured.\n")
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default=os.path.join(
            os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd()),
            "tmp", "repair_timing_runtime", "results",
        ),
    )
    args = parser.parse_args()
    sys.stdout.write(render(load_results(args.results)))


if __name__ == "__main__":
    main()
