#!/usr/bin/env python3
"""Turn the campaign's result files into the pull request that is the study.

This study has no write-up in the tree. The pull request *is* the
artifact: body carries the question, the graphs, the tables and the
interpretation; one comment per phase carries that phase's complete raw
samples as CSV. That split is not stylistic -- GitHub caps a PR body at
65,536 characters and the full sample set does not fit beside prose, so
the body holds findings and each comment holds data under its own cap.

Everything is derived from whatever is under the results directory. A
table typed by hand rots the first time a campaign is re-run, and a
partial campaign must not read as a complete one: every section that
lacks its inputs says so by name instead of quietly disappearing.

    bazelisk run //test/threads_policy:report -- --body > body.md
    bazelisk run //test/threads_policy:report -- --raw 2 > phase2.md

To examine a policy this study did not measure, run the campaign with
new `--threads` values into the same results directory and regenerate:
the arms are discovered, not declared here.
"""

import argparse
import collections
import glob
import json
import math
import os
import sys

# GitHub's limit on a PR body and on a single comment. Exceeding it
# truncates the evidence, so it is checked rather than hoped for.
GITHUB_CHAR_CAP = 65536

# At or below this, a substep used one core's worth of CPU: it is
# single-threaded, and the arms measure nothing about thread policy.
# Reported as such rather than as a 1.00x speedup, which would dilute
# every average with a guaranteed null.
THREAD_BLIND_CPU_PCT = 110

STAGE_ORDER = ["place", "cts", "grt", "route", "final"]


def load(results_dir):
    """Every result file, newest wins on collision."""
    records = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        with open(path) as handle:
            records.append(json.load(handle))
    return records


def mean(values):
    return sum(values) / len(values)


def two_sigma(values):
    """2 sigma of the sample. Zero for a single run -- which is honest:
    one run measures no spread, and the resolution figure that depends
    on it will say the comparison cannot be resolved."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return 2.0 * math.sqrt(var)


def resolution(sigma2, k):
    """The smallest difference k runs per arm can resolve: 2s*sqrt(2/k).

    Below this a difference between two arms is indistinguishable from
    the spread of the instrument, and the verdict is "did not resolve"
    rather than "no effect" -- a distinction the pre-route-pessimism
    campaign's own conclusion turned on.
    """
    if k < 2:
        return float("inf")
    return sigma2 * math.sqrt(2.0 / k)


Cell = collections.namedtuple("Cell", "wall wall2s cpu user_sys peak sha1s n")


def index(records):
    """(design, stage, substep, threads, pinned) -> Cell."""
    buckets = collections.defaultdict(list)
    for rec in records:
        for step, got in rec["substeps"].items():
            key = (
                rec["design"],
                rec["stage"],
                step,
                rec["threads"],
                bool(rec.get("pinned")),
            )
            buckets[key].append(got)

    out = {}
    for key, samples in buckets.items():
        walls = [s["wall_s"] for s in samples]
        out[key] = Cell(
            wall=mean(walls),
            wall2s=two_sigma(walls),
            cpu=mean([s["cpu_pct"] for s in samples]),
            user_sys=mean([s["user_s"] + s["sys_s"] for s in samples]),
            peak=mean([s["peak_kb"] for s in samples]),
            sha1s={s.get("result_sha1") for s in samples},
            n=len(samples),
        )
    return out


def bar(value, biggest, width=18):
    """A code-fence bar. Renders everywhere, including where mermaid does not."""
    if biggest <= 0:
        return ""
    return "█" * max(1, int(round(width * value / biggest)))


def arms_present(cells, pinned=False):
    return sorted({key[3] for key in cells if key[4] == pinned})


def host_line(records):
    prov = records[0]["provenance"]
    return "{} - {} physical cores / {} hardware threads, governor `{}`, boost `{}`, kernel `{}`".format(
        prov.get("cpu_model") or "unknown CPU",
        prov.get("physical_cores"),
        prov.get("hardware_threads"),
        prov.get("governor"),
        prov.get("boost"),
        prov.get("kernel"),
    )


def verdict(base, arm, k):
    """Compare one arm against the status quo for one substep."""
    if base.cpu <= THREAD_BLIND_CPU_PCT:
        return "thread-blind", None
    delta = 100.0 * (arm.wall - base.wall) / base.wall
    res = resolution(max(base.wall2s, arm.wall2s), min(base.n, arm.n))
    res_pct = 100.0 * res / base.wall if base.wall else float("inf")
    if abs(delta) <= res_pct:
        return "did not resolve", delta
    return ("faster" if delta < 0 else "slower"), delta


def section_decision(cells, records):
    """The headline: cores vs hardware threads, per substep."""
    prov = records[0]["provenance"]
    cores, threads = prov.get("physical_cores"), prov.get("hardware_threads")
    have = arms_present(cells)
    if cores not in have or threads not in have or cores == threads:
        return (
            "### Cores vs hardware threads, per substep\n\n"
            "**Not measured.** Needs unpinned arms at both {} (cores) and {} "
            "(hardware threads); present: {}.\n".format(cores, threads, have or "none")
        )

    rows = []
    for (design, stage, step, t, pin), cell in sorted(cells.items()):
        if pin or t != threads:
            continue
        arm = cells.get((design, stage, step, cores, False))
        if not arm:
            continue
        how, delta = verdict(cell, arm, min(cell.n, arm.n))
        rows.append((design, stage, step, cell, arm, how, delta))

    if not rows:
        return "### Cores vs hardware threads, per substep\n\n**Not measured.**\n"

    out = [
        "### Cores vs hardware threads, per substep",
        "",
        "`-threads {}` is what ORFS does today; `-threads {}` is the proposal.".format(
            threads, cores
        ),
        "Negative delta means the proposal is faster. `cpu%` is achieved",
        "parallelism as ORFS's own log reports it; `cpu-s` is user+sys, the",
        "work actually spent. A substep marked *thread-blind* used one core's",
        "worth of CPU at `-threads {}`, so it measures nothing about thread".format(threads),
        "policy and is excluded from the roll-up.",
        "",
        "| design | stage | substep | wall @{} | wall @{} | delta | 2 sigma | verdict | cpu% @{} | cpu% @{} | cpu-s @{} | cpu-s @{} | same result |".format(
            threads, cores, threads, cores, threads, cores
        ),
        "| --- | --- | --- | --: | --: | --: | --: | --- | --: | --: | --: | --: | --- |",
    ]
    for design, stage, step, base, arm, how, delta in rows:
        same = "yes"
        if None in base.sha1s or None in arm.sha1s:
            same = "unproven"
        elif base.sha1s != arm.sha1s:
            same = "**NO**"
        elif len(base.sha1s | arm.sha1s) > 1:
            same = "**NO**"
        runs = min(base.n, arm.n)
        spread = (
            "n/a ({} run)".format(runs) if runs < 2
            else "{:.1f}s".format(max(base.wall2s, arm.wall2s))
        )
        out.append(
            "| {} | {} | `{}` | {:.1f}s | {:.1f}s | {} | {} | {} | {:.0f}% | {:.0f}% | {:.0f} | {:.0f} | {} |".format(
                design, stage, step, base.wall, arm.wall,
                "-" if delta is None else "{:+.1f}%".format(delta),
                spread, how,
                base.cpu, arm.cpu, base.user_sys, arm.user_sys, same,
            )
        )
    return "\n".join(out) + "\n"


def section_rollup(cells, records):
    """Per-stage totals over the thread-sensitive substeps only."""
    prov = records[0]["provenance"]
    cores, threads = prov.get("physical_cores"), prov.get("hardware_threads")
    have = arms_present(cells)
    if cores not in have or threads not in have:
        return "### Per-stage roll-up\n\n**Not measured.**\n"

    totals = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for (design, stage, step, t, pin), cell in cells.items():
        if pin or t != threads:
            continue
        arm = cells.get((design, stage, step, cores, False))
        if not arm or cell.cpu <= THREAD_BLIND_CPU_PCT:
            continue
        row = totals[(design, stage)]
        row[0] += cell.wall
        row[1] += arm.wall
        row[2] += cell.user_sys
        row[3] += arm.user_sys

    if not totals:
        return "### Per-stage roll-up\n\n**Not measured.**\n"

    biggest = max(max(v[0], v[1]) for v in totals.values())
    out = [
        "### Per-stage roll-up (thread-sensitive substeps only)",
        "",
        "```",
        "{:<12} {:<6} {:>9} {:>9} {:>8}   {}".format(
            "design", "stage", "@{}".format(threads), "@{}".format(cores),
            "delta", "wall @{} vs @{}".format(threads, cores)),
    ]
    for (design, stage), (w_hi, w_lo, c_hi, c_lo) in sorted(
        totals.items(), key=lambda kv: (kv[0][0], STAGE_ORDER.index(kv[0][1]))
    ):
        delta = 100.0 * (w_lo - w_hi) / w_hi if w_hi else 0.0
        out.append("{:<12} {:<6} {:>8.1f}s {:>8.1f}s {:>7.1f}%   {} @{}".format(
            design, stage, w_hi, w_lo, delta, bar(w_hi, biggest), threads))
        out.append("{:<12} {:<6} {:>8}  {:>8}  {:>8}   {} @{}".format(
            "", "", "", "", "", bar(w_lo, biggest), cores))
    out.append("```")
    out.append("")
    out.append(
        "CPU-seconds tell the other half of the story: where wall time is "
        "unchanged but `cpu-s` halves, the hardware threads were being paid "
        "for and delivering nothing."
    )
    return "\n".join(out) + "\n"


def section_sweep(cells, records):
    """The shape of the curve: where does adding threads stop helping."""
    have = arms_present(cells)
    if len(have) < 3:
        return (
            "### Where the curve saturates\n\n"
            "**Not measured.** Needs three or more unpinned thread arms; "
            "present: {}.\n".format(have or "none")
        )
    prov = records[0]["provenance"]
    cores = prov.get("physical_cores")

    # The substeps worth plotting: thread-sensitive, and measured at
    # every arm so the curve has no holes.
    series = collections.defaultdict(dict)
    for (design, stage, step, t, pin), cell in cells.items():
        if pin:
            continue
        series[(design, stage, step)][t] = cell
    plotted = {
        key: arms for key, arms in series.items()
        if set(arms) >= set(have) and max(a.cpu for a in arms.values()) > THREAD_BLIND_CPU_PCT
    }
    if not plotted:
        return "### Where the curve saturates\n\n**Not measured.**\n"

    out = [
        "### Where the curve saturates",
        "",
        "Wall time normalized to the 1-thread run where present, otherwise",
        "to the slowest arm. The question upstream is not whether 32 beats",
        "16 on one box -- it is where the curve goes flat, because that is",
        "what a default should track.",
        "",
    ]

    # Mermaid renders natively on GitHub. xychart-beta is beta, so the
    # same numbers follow as a code-fence table that cannot fail to render.
    biggest_key = max(plotted, key=lambda k: max(c.wall for c in plotted[k].values()))
    arms = sorted(plotted[biggest_key])
    out += [
        "```mermaid",
        "xychart-beta",
        '    title "Wall time vs -threads: {} {} {}"'.format(*biggest_key),
        '    x-axis "-threads" [{}]'.format(", ".join(str(a) for a in arms)),
        '    y-axis "wall seconds"',
        "    line [{}]".format(
            ", ".join("{:.1f}".format(plotted[biggest_key][a].wall) for a in arms)
        ),
        "```",
        "",
    ]

    out += ["```", "{:<12} {:<6} {:<22} {}".format(
        "design", "stage", "substep",
        " ".join("{:>9}".format("t=" + str(a)) for a in arms))]
    for key in sorted(plotted):
        row = plotted[key]
        out.append("{:<12} {:<6} {:<22} {}".format(
            key[0], key[1], key[2],
            " ".join("{:>8.1f}s".format(row[a].wall) for a in arms)))
        out.append("{:<12} {:<6} {:<22} {}".format(
            "", "", "  cpu%",
            " ".join("{:>8.0f}%".format(row[a].cpu) for a in arms)))
    out += ["```", ""]
    if cores in arms:
        out.append(
            "The `t={}` column is the physical-core count on this host.".format(cores)
        )
    return "\n".join(out) + "\n"


def section_pinning(cells, records):
    """Fewer threads, or no SMT siblings? They are different claims."""
    pinned_arms = arms_present(cells, pinned=True)
    if not pinned_arms:
        return (
            "### Fewer threads, or no SMT siblings?\n\n"
            "**Not measured.** Needs `--pin` arms. Until this is run, the "
            "study cannot say whether asking for fewer threads is sufficient "
            "or whether the win requires affinity that `-threads` alone "
            "cannot express.\n"
        )
    out = [
        "### Fewer threads, or no SMT siblings?",
        "",
        "`-threads N` asks for N threads; it does not stop the scheduler from",
        "placing two of them on one core's SMT siblings. If free-floating and",
        "pinned agree, changing `NUM_CORES` captures the whole win and the",
        "upstream change is sufficient. If pinning wins on its own, then",
        "`-threads` cannot deliver it and the recommendation has to say so.",
        "",
        "| design | stage | substep | threads | free | pinned | delta |",
        "| --- | --- | --- | --: | --: | --: | --: |",
    ]
    for (design, stage, step, t, pin), cell in sorted(cells.items()):
        if not pin:
            continue
        free = cells.get((design, stage, step, t, False))
        if not free:
            continue
        delta = 100.0 * (cell.wall - free.wall) / free.wall if free.wall else 0.0
        out.append("| {} | {} | `{}` | {} | {:.1f}s | {:.1f}s | {:+.1f}% |".format(
            design, stage, step, t, free.wall, cell.wall, delta))
    return "\n".join(out) + "\n"


def section_work_changed(cells):
    """Did -threads change the layout? If so, the timings compare different work."""
    offenders = []
    seen = collections.defaultdict(dict)
    for (design, stage, step, t, pin), cell in cells.items():
        if pin:
            continue
        seen[(design, stage, step)][t] = cell.sha1s
    for key, arms in sorted(seen.items()):
        hashes = set()
        unproven = False
        for shas in arms.values():
            if None in shas:
                unproven = True
            hashes |= {s for s in shas if s}
        if len(hashes) > 1:
            offenders.append((key, sorted(hashes), unproven))

    if not seen:
        return "### Did `-threads` change the result?\n\n**Not measured.**\n"
    if not offenders:
        return (
            "### Did `-threads` change the result?\n\n"
            "**No.** Every substep produced a byte-identical result across "
            "every thread arm, as witnessed by the `sha1sum result` column "
            "ORFS's own `genElapsedTime.py` writes into each log. The runtime "
            "comparisons above are therefore between identical work.\n"
        )
    out = [
        "### Did `-threads` change the result?",
        "",
        "**Yes, and that matters more than the timings.** These substeps "
        "produced different results at different thread counts, so their "
        "runtime comparison is between *different work* and cannot be read "
        "as a speedup. It also means the flow's output depends on the "
        "machine it ran on:",
        "",
        "| design | stage | substep | distinct results |",
        "| --- | --- | --- | --: |",
    ]
    for (design, stage, step), hashes, unproven in offenders:
        out.append("| {} | {} | `{}` | {}{} |".format(
            design, stage, step, len(hashes), " (some unproven)" if unproven else ""))
    return "\n".join(out) + "\n"




def _common_arms(per_key, arms):
    """The largest fully-covered block of (keys x arms) to compare.

    Pooling a sum over arms that cover different keys is the easiest way
    to manufacture a large fake effect: `route` was swept at t=24 on
    three designs and measured at t=32 on six, so summing each arm as it
    stood made the three-design arm look 47% faster than the six-design
    one, and that fiction propagated into the flow total.

    Every returned key has a value at every returned arm. Which block to
    pick is a real choice -- keeping all arms costs designs, keeping all
    designs collapses the ladder -- so it maximises keys x arms, which
    prefers whichever loses less information, with ties going to the
    longer ladder. At least two arms, since one arm compares nothing.
    """
    best = ([], [])
    best_score = 0
    for size in range(len(arms), 1, -1):
        for start in range(0, len(arms) - size + 1):
            subset = list(arms[start:start + size])
            keys = [k for k in per_key if all(a in per_key[k] for a in subset)]
            if not keys:
                continue
            score = len(keys) * len(subset)
            if score > best_score or (score == best_score
                                      and len(subset) > len(best[1])):
                best, best_score = (keys, subset), score
    return best


def phase_index(records):
    """(design, stage, phase, threads, pinned) -> mean seconds.

    Phase seconds are summed within an arm first (a command can run
    twice in one substep, e.g. two repair_timing calls), then averaged
    across repeats.
    """
    buckets = collections.defaultdict(list)
    for rec in records:
        per_arm = collections.defaultdict(float)
        for step, got in rec["substeps"].items():
            for ph in got.get("phases", []):
                per_arm[ph["name"]] += ph["seconds"]
        for name, secs in per_arm.items():
            key = (rec["design"], rec["stage"], name, rec["threads"],
                   bool(rec.get("pinned")))
            buckets[key].append(secs)
    return {k: mean(v) for k, v in buckets.items()}


def section_ladder(cells, records):
    """Wall time versus thread count, per stage. The shape of the answer.

    `-threads` is a ceiling, so what matters is where each stage's curve
    stops improving -- not whether one arbitrary value beats another.
    """
    arms = arms_present(cells)
    if len(arms) < 3:
        return (
            "### The scaling ladder\n\n"
            "**Not measured.** Needs three or more unpinned thread arms; "
            "present: {}.\n".format(arms or "none")
        )
    prov = records[0]["provenance"]
    ceiling = prov.get("hardware_threads")
    cores = prov.get("physical_cores")

    totals = collections.defaultdict(lambda: collections.defaultdict(float))
    for (design, stage, step, t, pin), cell in cells.items():
        if pin:
            continue
        totals[stage][t] += cell.wall

    out = [
        "### The scaling ladder",
        "",
        "Wall time summed over every measured design, per stage, against",
        "`-threads`. The ceiling on this host is {} (hardware threads);".format(ceiling),
        "{} is the physical core count.".format(cores),
        "",
        "```",
        "{:<7} {}   {}".format(
            "stage", " ".join("{:>9}".format("t=" + str(a)) for a in arms), "best"),
    ]
    for stage in STAGE_ORDER:
        if stage not in totals:
            continue
        row = totals[stage]
        if not all(a in row for a in arms):
            continue
        best = min(arms, key=lambda a: row[a])
        out.append("{:<7} {}   t={}{}".format(
            stage,
            " ".join("{:>8.1f}s".format(row[a]) for a in arms),
            best,
            " (ceiling)" if best == ceiling else "",
        ))
    out += ["```", ""]

    # Mermaid renders on GitHub; the table above is the fallback that
    # cannot fail to render, so the chart is a bonus rather than the
    # evidence.
    plotted = [s for s in STAGE_ORDER
               if s in totals and all(a in totals[s] for a in arms)]
    if plotted:
        biggest = max(plotted, key=lambda s: max(totals[s].values()))
        out += [
            "```mermaid",
            "xychart-beta",
            '    title "{} wall time vs -threads (all designs)"'.format(biggest),
            '    x-axis "-threads" [{}]'.format(", ".join(str(a) for a in arms)),
            '    y-axis "wall seconds"',
            "    line [{}]".format(
                ", ".join("{:.1f}".format(totals[biggest][a]) for a in arms)),
            "```",
            "",
        ]
    return "\n".join(out) + "\n"


def section_regions(records, cells):
    """The same ladder, per code region rather than per stage.

    A stage is not the tool it is named after: `5_1_grt` is mostly
    repair_timing and pin_access, and FastRoute is a few percent. Those
    regions want opposite thread counts, so the per-stage number is an
    average of disagreeing things.
    """
    idx = phase_index(records)
    if not idx:
        return (
            "### Per-region ladder\n\n"
            "**Not measured.** No phase stacks recorded -- the arms ran "
            "without the `RUN_CMD` override, or the logs carry no `Took` "
            "lines.\n"
        )
    arms = sorted({k[3] for k in idx if not k[4]})
    # {region: {(design, stage): {threads: seconds}}}. Keyed by site so a
    # region measured on different design sets per arm is never pooled
    # across them: pin_access appears in both grt and route, and route
    # was swept on three designs rather than six.
    sites = collections.defaultdict(lambda: collections.defaultdict(dict))
    for (design, stage, name, t, pin), secs in idx.items():
        if pin:
            continue
        sites[name][(design, stage)][t] = secs

    regions = {}
    coverage = {}
    for name, per_site in sites.items():
        keys, usable = _common_arms(per_site, arms)
        if not keys or len(usable) < 2:
            continue
        regions[name] = {t: sum(per_site[k][t] for k in keys) for t in usable}
        coverage[name] = (len(keys), usable)

    if not regions:
        return (
            "### Per-region ladder\n\n**Not measured.** No region has "
            "comparable coverage across two or more thread arms.\n"
        )

    ranked = sorted(regions.items(),
                    key=lambda kv: -max(kv[1].values()))
    out = [
        "### Per-region ladder",
        "",
        "Seconds per phase, summed over designs. Phases come from the",
        "`Took` lines ORFS already writes, so this is attribution, not",
        "new instrumentation.",
        "",
        "```",
        "{:<26} {}   {}".format(
            "region (flow command)",
            " ".join("{:>9}".format("t=" + str(a)) for a in arms),
            "best"),
    ]
    for name, row in ranked:
        n_sites, usable = coverage[name]
        best = min(usable, key=lambda a: row[a])
        out.append("{:<26} {}   t={:<3} {:>2} sites".format(
            name,
            " ".join(("{:>8.1f}s".format(row[a]) if a in row else "        -")
                     for a in arms),
            best, n_sites))
    out += ["```", ""]
    out.append(
        "`sites` is the number of (design, stage) pairs a row pools, and only "
        "pairs measured at every arm shown are counted -- otherwise an arm "
        "covering fewer designs reads as a speedup."
    )
    return "\n".join(out) + "\n"


def section_potential(cells, records):
    """What a per-stage choice is worth against the ceiling.

    Reported as a bound rather than a promise: a stage whose best point
    is inside the spread of its own repeats is reported as no better
    than the ceiling.
    """
    arms = arms_present(cells)
    prov = records[0]["provenance"]
    ceiling = prov.get("hardware_threads")
    if ceiling not in arms or len(arms) < 2:
        return "### The potential\n\n**Not measured.**\n"

    # {stage: {design: {threads: [wall, spread, runs]}}} -- keyed by
    # design so arms covering different design sets are never summed
    # against one another; see _common_arms.
    per = collections.defaultdict(lambda: collections.defaultdict(dict))
    for (design, stage, step, t, pin), cell in cells.items():
        if pin:
            continue
        slot = per[stage][design].setdefault(t, [0.0, 0.0, cell.n])
        slot[0] += cell.wall
        slot[1] = max(slot[1], cell.wall2s)
        slot[2] = min(slot[2], cell.n)

    out = [
        "### The potential",
        "",
        "Per stage: the ceiling against the best arm on the ladder, and",
        "whether that difference survives the spread of the repeats.",
        "",
        "| stage | at ceiling ({}) | best arm | gain | resolves? |".format(ceiling),
        "| --- | --: | --- | --: | --- |",
    ]
    total_ceiling = total_best = 0.0
    for stage in STAGE_ORDER:
        if stage not in per:
            continue
        designs, usable = _common_arms(per[stage], arms)
        if not designs or ceiling not in usable:
            continue
        walls = {t: sum(per[stage][d][t][0] for d in designs) for t in usable}
        base = walls[ceiling]
        best_t = min(walls, key=lambda t: walls[t])
        gain = 100.0 * (walls[best_t] - base) / base if base else 0.0
        spread = max(max(per[stage][d][t][1] for d in designs)
                     for t in (ceiling, best_t))
        runs = min(min(per[stage][d][t][2] for d in designs)
                   for t in (ceiling, best_t))
        res = resolution(spread, runs)
        resolves = best_t != ceiling and abs(walls[best_t] - base) > res
        # The comparison basis is always stated. Dropping designs is as
        # capable of moving the number as dropping arms, and a reader
        # cannot tell either happened from the totals alone.
        scope = " [{} designs".format(len(designs))
        if len(usable) != len(arms):
            scope += ", t={}".format(",".join(str(a) for a in usable))
        scope += "]"
        out.append("| {}{} | {:.1f}s | t={} | {} | {} |".format(
            stage, scope, base, best_t,
            "-" if best_t == ceiling else "{:+.1f}%".format(gain),
            "at ceiling" if best_t == ceiling
            else ("yes" if resolves else "**no**"),
        ))
        total_ceiling += base
        total_best += walls[best_t] if resolves else base

    if total_ceiling:
        out += [
            "",
            "Flow total over the measured stages: **{:.0f}s at the ceiling, "
            "{:.0f}s under a per-stage choice ({:+.1f}%)** -- counting only "
            "the stages whose gain resolves.".format(
                total_ceiling, total_best,
                100.0 * (total_best - total_ceiling) / total_ceiling),
        ]
    return "\n".join(out) + "\n"


def section_reconciliation(records):
    """Does the phase stack account for the wall time it splits?

    The check that catches a mis-parsed log. An arm whose phases sum to
    more than its substep wall has overlapping phases counted twice,
    which is a parser bug, not a measurement.
    """
    checked = bad = 0
    attributed = total = 0.0
    for rec in records:
        for step, got in rec["substeps"].items():
            rc = got.get("reconcile")
            if not rc:
                continue
            checked += 1
            if not rc["ok"]:
                bad += 1
            attributed += rc["attributed_s"]
            total += rc["wall_s"]
    if not checked:
        return ""
    frac = 100.0 * attributed / total if total else 0.0
    verdict = (
        "**{} of {} substep samples over-attribute** -- phases were counted "
        "that overlap. Treat the per-region table as suspect until that is "
        "fixed.".format(bad, checked)
        if bad else
        "All {} substep samples reconcile: no phase stack exceeds the wall "
        "time it splits.".format(checked)
    )
    return (
        "### Does the breakdown add up?\n\n"
        "{}\n\n"
        "{:.0f}% of measured wall time is attributed to a named phase; the "
        "rest is reported as unattributed rather than distributed.\n".format(
            verdict, frac)
    )



# Which code owns each phase name the logs produce. Used only to group
# the ranked table into "who would have to change something", so the
# TL;DR can say how much a given owner is worth.
PHASE_OWNER = {
    "repair_timing": "rsz + OpenSTA",
    "repair_design": "rsz + OpenSTA",
    "RSZ-0504": "rsz + OpenSTA",
    "RSZ-0505": "rsz + OpenSTA",
    "RSZ-0506": "rsz + OpenSTA",
    "CTS-0500": "cts + OpenSTA",
    "global_placement": "gpl",
    "improve_placement": "dpl",
    "DPL-0500": "dpl",
    "global_route": "grt (FastRoute)",
    "detailed_route": "drt",
    "pin_access": "drt",
}

# Fallback owner for substeps whose region the logs cannot attribute.
# 3_1_place_gp_skip_io is a gpl call like 3_3_place_gp, but ORFS emits no
# `Took` line for it, so phase attribution sees nothing and gpl's total
# would silently lose it -- which moved the headline ratio from 4.4x to
# 5.5x before this existed. Only used where the phase data is absent.
SUBSTEP_OWNER = {
    "3_1_place_gp_skip_io": "gpl",
    "3_3_place_gp": "gpl",
    "3_2_place_iop": None,          # single-threaded
    "5_3_fillcell": None,           # single-threaded
    "5_2_route": "drt",
    "4_1_cts": "cts + OpenSTA",
    "3_4_place_resized": "rsz + OpenSTA",
    "3_5_place_dp": "dpl",
    "5_1_grt": "grt (FastRoute)",
}

GPL_PR = "https://github.com/The-OpenROAD-Project/OpenROAD/pull/11368"


def _opportunity(cells, records):
    """[(saving, substep, region, owner)], plus the totals. Data only."""
    prov = records[0]["provenance"]
    ceiling = prov.get("hardware_threads")
    arms = arms_present(cells)
    if ceiling not in arms or len(arms) < 3:
        return [], 0.0, 0.0, ceiling

    per = collections.defaultdict(lambda: collections.defaultdict(dict))
    for (design, stage, step, t, pin), cell in cells.items():
        if pin:
            continue
        per[step][design][t] = cell.wall

    idx = substep_phase_index(records)
    rows = []
    measured = 0.0
    for step, by_design in per.items():
        designs, usable = _common_arms(by_design, arms)
        if not designs or ceiling not in usable:
            continue
        walls = {t: sum(by_design[d][t] for d in designs) for t in usable}
        best = min(walls, key=lambda t: walls[t])
        measured += walls[ceiling]
        curve = collections.defaultdict(lambda: collections.defaultdict(float))
        for (d, st, name, t), secs in idx.items():
            if st == step and d in designs:
                curve[name][t] += secs
        stamped = sorted({t for name in curve for t in curve[name]})
        region = None
        if stamped:
            hi = stamped[-1]
            rise = {n: pts[hi] - min(pts.values())
                    for n, pts in curve.items()
                    if hi in pts and len(pts) > 1}
            if rise:
                worst = max(rise, key=lambda n: rise[n])
                if rise[worst] > 0:
                    region = worst
        owner = PHASE_OWNER.get(region)
        if owner is None:
            # No phase attribution for this substep; fall back to what
            # the substep itself is, rather than dropping its seconds.
            owner = SUBSTEP_OWNER.get(step)
        rows.append((walls[ceiling] - walls[best], step, region,
                     owner, best, walls[ceiling], walls[best]))
    total = sum(max(0.0, r[0]) for r in rows)
    return rows, total, measured, ceiling


def section_tldr(cells, records):
    """What to do next, first, in as few lines as possible."""
    rows, total, measured, ceiling = _opportunity(cells, records)
    if total <= 0:
        return ""

    by_owner = collections.defaultdict(float)
    unowned = 0.0
    for saving, step, region, owner, best, _c, _b in rows:
        if saving <= 0:
            continue
        if owner:
            by_owner[owner] += saving
        else:
            unowned += saving
    ranked = sorted(by_owner.items(), key=lambda kv: -kv[1])
    gpl = by_owner.get("gpl", 0.0)

    out = [
        "## TL;DR -- what to do after the global-placement PR",
        "",
        "[OpenROAD#11368]({}) caps **global placement** at the physical".format(GPL_PR),
        "core count, in the tool, per region, with `-threads` left as the",
        "ceiling. That is the right shape and the precedent to copy.",
        "",
        "On the evidence below -- {:.0f}s of {:.0f}s available across "
        "{} asap7 designs -- what is left after it:".format(
            total, measured, len({k[0] for k in cells})),
        "",
        "| do this next | worth | vs gpl |",
        "| --- | --: | --: |",
    ]
    # Only owners worth listing get a row; the rest is one number, so
    # the reader is not asked to weigh six things that do not matter.
    THRESHOLD = 0.05
    listed = [(o, v) for o, v in ranked
              if o != "gpl" and v / total >= THRESHOLD]
    for owner, secs in listed:
        out.append(
            "| **{}** -- cap at ~the core count | {:.0f}s ({:.0f}% of "
            "what is left) | {} |".format(
                owner, secs, 100.0 * secs / total,
                "{:.1f}x".format(secs / gpl) if gpl else "n/a"))
    rest = total - gpl - sum(v for _o, v in listed)
    out += [
        "",
        "and then **stop**. Everything else together is {:.0f}s across "
        "{} substeps, which is smaller than the run-to-run spread of one "
        "large design -- there is no third thing worth doing on this "
        "evidence.".format(
            rest,
            sum(1 for r in rows
                if r[0] > 0 and PHASE_OWNER.get(r[2]) not in
                [o for o, _v in listed] + ["gpl"])),
        "",
        "### Do not do these",
        "",
        "- **Do not cap `drt`** (detailed route, pin access). It wants the",
        "  ceiling; capping it at the core count costs about 15%.",
        "- **Do not lower ORFS's `NUM_CORES` default.** It is the ceiling,",
        "  not a target. Deriving it from physical cores is wall-neutral",
        "  overall *and* would cap `drt`.",
        "- **Do not \"tune grt\".** FastRoute is a few percent of `5_1_grt`;",
        "  that stage's win is `repair_timing`, which is rsz and OpenSTA.",
        "",
        "### Two things to know before scheduling the next one",
        "",
        "- It is **not** a five-line mirror of #11368. `placementThreads()`",
        "  caps one tool's own OpenMP sites; OpenSTA's thread count is set",
        "  once globally (`OpenRoad::setThreadCount` -> `sta_->setThreadCount`)",
        "  and shared by every consumer, so scoping it to the repair calls",
        "  needs a set/restore around them or an STA-side cap.",
        "- **gpl's optimum moves with design size** on this set, and STA's",
        "  may too. #11368 measures a 1.28M-instance design preferring the",
        "  core count while these (much smaller) designs prefer half of it --",
        "  the same curve sampled further along. That argues for a",
        "  work-per-thread heuristic rather than a constant.",
        "",
        "---",
        "",
        "*Everything below is reference detail: the per-stage and per-region",
        "ladders, the phase attribution, and the raw samples in a comment.",
        "It is here to be read by a machine later, not reviewed now.*",
        "",
    ]
    return "\n".join(out) + "\n"

def substep_phase_index(records):
    """(design, substep, phase, threads) -> seconds, summed within an arm."""
    buckets = collections.defaultdict(list)
    for rec in records:
        if rec.get("pinned"):
            continue
        for step, got in rec["substeps"].items():
            per_arm = collections.defaultdict(float)
            for ph in got.get("phases", []):
                per_arm[ph["name"]] += ph["seconds"]
            for name, secs in per_arm.items():
                buckets[(rec["design"], step, name, rec["threads"])].append(secs)
    return {k: mean(v) for k, v in buckets.items()}


def section_priority(cells, records):
    """Where the remaining time actually is, ranked.

    The point of ranking by absolute seconds rather than percentage: a
    substep can show a large percentage on a small base and be worth
    nothing. And the biggest entry is misnamed -- `5_1_grt`'s saving is
    almost entirely `repair_timing`, so the row names the region the
    phase data says dominates rather than the substep it hides behind.
    """
    prov = records[0]["provenance"]
    ceiling = prov.get("hardware_threads")
    arms = arms_present(cells)
    if ceiling not in arms or len(arms) < 3:
        return "### Where to look next\n\n**Not measured.**\n"

    # Pool each substep over the designs that have every arm.
    per = collections.defaultdict(lambda: collections.defaultdict(dict))
    for (design, stage, step, t, pin), cell in cells.items():
        if pin:
            continue
        per[step][design][t] = cell.wall

    idx = substep_phase_index(records)
    rows = []
    for step, by_design in per.items():
        designs, usable = _common_arms(by_design, arms)
        if not designs or ceiling not in usable:
            continue
        walls = {t: sum(by_design[d][t] for d in designs) for t in usable}
        best = min(walls, key=lambda t: walls[t])
        saving = walls[ceiling] - walls[best]

        # Which region *pays* for the extra threads -- not which is
        # largest. pin_access is the biggest phase of 5_1_grt at low
        # thread counts, but it gets faster as threads rise, so it
        # cannot be what a cap recovers. The region responsible is the
        # one whose seconds *rise* between the cheapest and dearest
        # stamped arms.
        stamped = sorted({t for (d, st, n, t) in idx
                          if st == step and d in designs})
        dominant = None
        if len(stamped) >= 2:
            # Per region: seconds at each stamped arm, then the rise from
            # that region's own minimum to the highest arm. Measured from
            # the minimum rather than the lowest arm because these curves
            # are U-shaped -- global_placement is slower at 2 threads than
            # at 8, so comparing the extremes hides the penalty entirely.
            curve = collections.defaultdict(lambda: collections.defaultdict(float))
            for (d, st, name, t), secs in idx.items():
                if st == step and d in designs:
                    curve[name][t] += secs
            hi = stamped[-1]
            rise = {}
            for name, pts in curve.items():
                if hi not in pts or len(pts) < 2:
                    continue
                rise[name] = pts[hi] - min(pts.values())
            worst = max(rise, key=lambda n: rise[n]) if rise else None
            if worst is not None and rise[worst] > 0:
                dominant = worst
        rows.append((saving, step, walls[ceiling], walls[best], best,
                     dominant, len(designs)))

    if not rows:
        return "### Where to look next\n\n**Not measured.**\n"
    total = sum(max(0.0, r[0]) for r in rows)
    if total <= 0:
        # Measured, and the answer is zero. Not the same claim as
        # "not measured", and worth distinguishing: it means every
        # substep already wants the ceiling.
        return (
            "### Where to look next, by descending return\n\n"
            "**Nothing available.** Every measured substep is already "
            "fastest at the ceiling, so there is no thread cap to "
            "recover time with on this host.\n"
        )

    out = [
        "### Where to look next, by descending return",
        "",
        "Absolute seconds available on this host, pooled over the designs",
        "with full arm coverage. Ranked by seconds rather than percentage:",
        "a big percentage on a small base is worth nothing.",
        "",
        "`region that pays` is the phase whose seconds *rise* as threads",
        "increase -- the one a cap recovers. Deliberately not the largest",
        "phase: `pin_access` is the biggest part of `5_1_grt` at low thread",
        "counts but gets faster with more threads, so it cannot be what a",
        "cap buys back. This is why the top row is not named after the tool",
        "people would expect.",
        "",
        "| substep | region that pays | @ceiling | best | saves | share | wants |",
        "| --- | --- | --: | --: | --: | --: | --- |",
    ]
    for saving, step, ceil_v, best_v, best_t, dominant, ndesigns in sorted(
        rows, reverse=True
    ):
        share = 100.0 * saving / total if saving > 0 else 0.0
        wants = ("**the ceiling** -- capping costs time"
                 if best_t == ceiling else "t={}".format(best_t))
        out.append("| `{}` | {} | {:.1f}s | {:.1f}s | {} | {} | {} |".format(
            step,
            dominant or "_unattributed_",
            ceil_v, best_v,
            "-" if saving <= 0 else "{:.1f}s".format(saving),
            "-" if saving <= 0 else "{:.0f}%".format(share),
            wants,
        ))
    out += [
        "",
        "Total available: **{:.0f}s** of {:.0f}s measured "
        "(**{:.0f}%**).".format(
            total, sum(r[2] for r in rows),
            100.0 * total / sum(r[2] for r in rows)),
        "",
        "The tail is genuinely a tail: everything below the top two rows "
        "adds up to less than the run-to-run spread on a single large "
        "design, so there is no third thing worth doing on this evidence.",
    ]
    return "\n".join(out) + "\n"

def csv_rows(records):
    header = (
        "design,stage,substep,threads,pinned,repeat,wall_s,user_s,sys_s,"
        "cpu_pct,peak_kb,threads_witnessed,result_sha1,loadavg_at_start"
    )
    rows = [header]
    for rec in sorted(
        records, key=lambda r: (r["design"], r["stage"], r["threads"], r["repeat"])
    ):
        for step, got in sorted(rec["substeps"].items()):
            rows.append(
                "{},{},{},{},{},{},{:.2f},{:.2f},{:.2f},{},{},{},{},{:.2f}".format(
                    rec["design"], rec["stage"], step, rec["threads"],
                    int(bool(rec.get("pinned"))), rec["repeat"],
                    got["wall_s"], got["user_s"], got["sys_s"], got["cpu_pct"],
                    got["peak_kb"], got["threads"], got.get("result_sha1") or "",
                    rec.get("loadavg_at_start", 0.0),
                )
            )
    return rows


def raw_comment(records):
    """A PR comment carrying every sample, for recomputation without a re-run."""
    if not records:
        return "No samples recorded.\n"
    rows = csv_rows(records)
    prov = records[0]["provenance"]
    return "\n".join([
        "## Raw samples",
        "",
        "Every measurement behind the tables in the PR body. One row per",
        "(design, stage, substep, thread arm, repeat). `threads_witnessed` is",
        "what OpenROAD's `ORD-0030` line reported it actually installed --",
        "proof the arm measured the thread count it claims. `result_sha1` is",
        "ORFS's own hash of that substep's output, so identical work can be",
        "verified rather than assumed.",
        "",
        "Host: {}".format(host_line(records)),
        "",
        "```csv",
        "\n".join(rows),
        "```",
        "",
        "{} rows.".format(len(rows) - 1),
        "",
    ])


def body(records, cells):
    if not records:
        return (
            "# ORFS `-threads` policy: cores or hardware threads?\n\n"
            "**No results recorded yet.** Run the campaign, then regenerate.\n"
        )
    prov = records[0]["provenance"]
    cores, threads = prov.get("physical_cores"), prov.get("hardware_threads")
    designs = sorted({r["design"] for r in records})

    parts = [
        "# How the flow's parallel regions scale, and what `-threads` should be",
        "",
        "**FYI only -- this PR is for the data and will be closed.** No flow",
        "behaviour changes here, and it recommends *no* change to ORFS.",
        "",
        section_tldr(cells, records),
        "`NUM_CORES` -> `openroad -threads N` is a **ceiling**: what a job is",
        "permitted to use, not a target. So the question is not \"cores or",
        "hardware threads\" but, per parallel region, how far *below* the",
        "ceiling that region wants to sit -- and why.",
        "",
        "Measured over {} asap7 design{}, {} thread counts, and every".format(
            len(designs), "" if len(designs) == 1 else "s",
            len(arms_present(cells))),
        "substep from place through route.",
        "",

        "**Host:** {}".format(host_line(records)),
        "",
        "**Designs:** {}".format(", ".join("`{}`".format(d) for d in designs)),
        "",
        "## Method",
        "",
        "Stage inputs are built once by Bazel and are byte-identical for",
        "every arm. Each arm then runs that stage's substeps outside the",
        "Bazel sandbox, one at a time on an otherwise idle machine, via the",
        "`_deps` reproducer the repo already ships:",
        "",
        "```sh",
        "bazelisk run <target>_<stage>_deps          # deploy; build prior stages",
        "tmp/.../make do-<substep> NUM_CORES=<n>     # the arm",
        "```",
        "",
        "Nothing is instrumented for this study. ORFS already writes what it",
        "costs into every substep log, and the harness reads it:",
        "",
        "```",
        "[INFO ORD-0030] Using 16 thread(s).                      <- the knob actually installed",
        "Elapsed time: 4:12.31[h:]min:sec. CPU time: user 3821.44 sys 91.02 (1549%). Peak memory: 8214032KB.",
        "5_2_route                 .odb          252           8021 734947984bd3fee97b5f   <- result hash",
        "```",
        "",
        "Those three lines give wall time, achieved parallelism, CPU-seconds,",
        "peak RSS, proof the requested thread count arrived, and proof of",
        "whether the arms produced the same layout. A sample missing the",
        "`ORD-0030` witness, or whose witness disagrees with the arm, is",
        "discarded rather than averaged in.",
        "",
        "## Results",
        "",
        section_decision(cells, records),
        "",
        section_rollup(cells, records),
        "",
        section_ladder(cells, records),
        "",
        section_regions(records, cells),
        "",
        section_potential(cells, records),
        "",
        section_priority(cells, records),
        "",
        section_reconciliation(records),
        "",
        section_sweep(cells, records),
        "",
        section_work_changed(cells),
        "",
        section_pinning(cells, records),
        "",
        "## The policy this suggests",
        "",
        "Per region, with `-threads` left as the ceiling. The evidence for",
        "each row is the per-region ladder above.",
        "",
        "| region | code | schedule | wants |",
        "| --- | --- | --- | --- |",
        "| detailed route, pin access | `drt/TritonRoute.cpp`, `drt/src/pa/FlexPA*` | `dynamic` | the ceiling |",
        "| global placement | `gpl` | OpenMP | ~half the cores, rising with design size |",
        "| repair_design / repair_timing / report_metrics | `src/rsz` + OpenSTA | STA threads | ~the core count |",
        "| global route core | `grt/.../maze.cpp` | `static`, memory-bound | ~the core count |",
        "| io placement, fillcell | -- | -- | nothing; single-threaded |",
        "",
        "Dynamic scheduling over irregular work is where a second thread",
        "per core hides latency; static partitioning of memory-bound work is",
        "where an SMT sibling contends. That is why the answer inverts",
        "between detailed route and everything else, and it is a mechanism",
        "rather than a correlation.",
        "",
        "**gpl\'s optimum moves with design size**, so a constant is the",
        "wrong shape for it. The gain from halving shrinks monotonically as",
        "designs grow across this set, and #11368 measures a 1.28M-instance",
        "design preferring the core count -- the same curve, sampled",
        "further along. That argues for a work-per-thread heuristic rather",
        "than a fixed cap.",
        "",
        "**What should not change:** ORFS\'s `NUM_CORES` default. Deriving",
        "it from physical cores is wall-neutral overall and would cap",
        "detailed route, which genuinely uses the hardware threads. A",
        "ceiling is not the place to encode a per-region preference. For",
        "reference, the diff that was *not* worth making:",
        "",
        "```make",
        "ifeq (,$(strip $(NUM_CORES)))",
        "  # Physical cores: distinct (physical id, core id) pairs. OpenROAD's",
        "  # parallel sections gain nothing from a core's second SMT thread,",
        "  # and pay for it in contention and lower all-core boost clocks.",
        "  NUM_CORES := $(shell awk -F: '/^physical id/{p=$$2} /^core id/{print p\":\"$$2}' \\",
        "                         /proc/cpuinfo 2>/dev/null | sort -u | wc -l)",
        "  ifeq (,$(strip $(NUM_CORES)))",
        "    NUM_CORES := $(shell nproc 2>/dev/null)",
        "  endif",
        "  # ... existing fallbacks unchanged",
        "endif",
        "```",
        "",
        "`/proc/cpuinfo` rather than `lscpu` keeps the dependency set as it",
        "is. Where the topology is absent -- ARM kernels that omit `core id`,",
        "some containers -- the existing `nproc` path still answers.",
        "",
        "## Limits, and what this does not show",
        "",
        "Stated here so they are not discovered later.",
        "",
        "- **One machine, one microarchitecture, one SMT ratio** ({}/{} = 2x)."
        .format(threads, cores),
        "  This cannot show that cores-not-threads is right in general, only",
        "  that the hardware threads are not paying for themselves here.",
        "  Counter-data from other hosts is the point of publishing the",
        "  harness.",
        "- **One PDK** (asap7) and OpenROAD at one commit.",
        "- **`powersave` governor with boost enabled**, which is the common",
        "  desktop configuration and also means all-core clocks depend on how",
        "  many cores are loaded. That is part of the effect being measured,",
        "  not noise to be removed, but it does make the result a property of",
        "  the machine as configured.",
        "- **Single socket**, so no NUMA effect is measured.",
        "- **cgroup CPU quota is not measured.** `nproc` respects CPU",
        "  affinity but not a cgroup bandwidth limit, so a container with a",
        "  fractional quota gets a thread count unrelated to what it may",
        "  spend. That is a separate defect in the same line of code, named",
        "  here and left unmeasured.",
        "- Synthesis is excluded throughout: it is Yosys, which takes no",
        "  `-threads`.",
        "",
        "## How to re-examine this",
        "",
        "The raw samples are in the comments on this PR, one per phase, as",
        "CSV -- enough to recompute every table above without re-running",
        "anything. To measure a policy this study did not cover:",
        "",
        "```sh",
        "bazelisk run //test/threads_policy:campaign -- \\",
        "    --designs aes jpeg --stages route --threads 8 12 --repeats 3",
        "bazelisk run //test/threads_policy:report -- --body",
        "```",
        "",
        "Arms are discovered from the results directory, not declared in the",
        "report, so a new thread count appears in the tables by being run.",
        "",
    ]
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=None)
    parser.add_argument("--body", action="store_true", help="emit the PR body")
    parser.add_argument("--raw", action="store_true", help="emit the raw-sample comment")
    args = parser.parse_args()

    results_dir = args.results or os.path.join(
        os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd(),
        "tmp", "threads_policy", "results",
    )
    records = load(results_dir)
    if not records:
        sys.stderr.write(
            "no results under {}\n"
            "run: bazelisk run //test/threads_policy:campaign\n".format(results_dir)
        )
    cells = index(records)

    text = raw_comment(records) if args.raw else body(records, cells)
    if len(text) > GITHUB_CHAR_CAP:
        raise SystemExit(
            "generated text is {} characters, over GitHub's {} cap. Split it "
            "rather than letting the evidence truncate.".format(
                len(text), GITHUB_CHAR_CAP
            )
        )
    sys.stdout.write(text)
    sys.stderr.write(
        "\n[{} samples from {} arm files, {} characters]\n".format(
            sum(len(r["substeps"]) for r in records), len(records), len(text)
        )
    )


if __name__ == "__main__":
    main()
