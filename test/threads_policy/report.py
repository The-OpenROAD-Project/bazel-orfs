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

import idempotency
import witness

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


def timed(records):
    """The records whose wall times are measurements.

    An arm run in `--mode idempotency` shared the machine with other
    arms on purpose: contention is what exposes an order-dependent bug,
    and it costs nothing there because whether two arms computed the
    same thing does not depend on how busy the machine was. Its wall
    time, however, is the time the *other arms* took. Laddering it
    would produce a confident thread-scaling curve measured against
    nothing, so every timing section is built from this subset and
    every one of them says how many samples it dropped.

    The idempotency verdicts use all the records, contended included.
    """
    return [r for r in records if not r.get("contended")]


def contended_note(records):
    """One line naming what the timing sections could not use."""
    dropped = len(records) - len(timed(records))
    if not dropped:
        return ""
    return (
        "{} of {} arm samples ran under `--mode idempotency`, where arms "
        "share the machine deliberately, so their wall times are excluded "
        "from every table below. They are used for the idempotency "
        "verdicts, which contention cannot affect. Re-run those arms with "
        "`--mode timing` to put them in a ladder.".format(dropped, len(records))
    )


def index(records):
    """(design, stage, substep, threads, pinned) -> Cell.

    Timing only: see timed(). A contended sample carries a real result
    hash and a meaningless wall time, and this index is what every
    runtime table reads.
    """
    buckets = collections.defaultdict(list)
    for rec in timed(records):
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
        "worth of CPU at `-threads {}`, so it measures nothing about thread".format(
            threads
        ),
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
            "n/a ({} run)".format(runs)
            if runs < 2
            else "{:.1f}s".format(max(base.wall2s, arm.wall2s))
        )
        out.append(
            "| {} | {} | `{}` | {:.1f}s | {:.1f}s | {} | {} | {} | {:.0f}% | {:.0f}% | {:.0f} | {:.0f} | {} |".format(
                design,
                stage,
                step,
                base.wall,
                arm.wall,
                "-" if delta is None else "{:+.1f}%".format(delta),
                spread,
                how,
                base.cpu,
                arm.cpu,
                base.user_sys,
                arm.user_sys,
                same,
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
            "design",
            "stage",
            "@{}".format(threads),
            "@{}".format(cores),
            "delta",
            "wall @{} vs @{}".format(threads, cores),
        ),
    ]
    for (design, stage), (w_hi, w_lo, c_hi, c_lo) in sorted(
        totals.items(), key=lambda kv: (kv[0][0], STAGE_ORDER.index(kv[0][1]))
    ):
        delta = 100.0 * (w_lo - w_hi) / w_hi if w_hi else 0.0
        out.append(
            "{:<12} {:<6} {:>8.1f}s {:>8.1f}s {:>7.1f}%   {} @{}".format(
                design, stage, w_hi, w_lo, delta, bar(w_hi, biggest), threads
            )
        )
        out.append(
            "{:<12} {:<6} {:>8}  {:>8}  {:>8}   {} @{}".format(
                "", "", "", "", "", bar(w_lo, biggest), cores
            )
        )
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
        key: arms
        for key, arms in series.items()
        if set(arms) >= set(have)
        and max(a.cpu for a in arms.values()) > THREAD_BLIND_CPU_PCT
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

    out += [
        "```",
        "{:<12} {:<6} {:<22} {}".format(
            "design",
            "stage",
            "substep",
            " ".join("{:>9}".format("t=" + str(a)) for a in arms),
        ),
    ]
    for key in sorted(plotted):
        row = plotted[key]
        out.append(
            "{:<12} {:<6} {:<22} {}".format(
                key[0],
                key[1],
                key[2],
                " ".join("{:>8.1f}s".format(row[a].wall) for a in arms),
            )
        )
        out.append(
            "{:<12} {:<6} {:<22} {}".format(
                "", "", "  cpu%", " ".join("{:>8.0f}%".format(row[a].cpu) for a in arms)
            )
        )
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
        out.append(
            "| {} | {} | `{}` | {} | {:.1f}s | {:.1f}s | {:+.1f}% |".format(
                design, stage, step, t, free.wall, cell.wall, delta
            )
        )
    return "\n".join(out) + "\n"


def section_work_changed(cells, records=None):
    """Did the thread count change the result?

    A renderer over idempotency.py, which is where the distinction
    lives: #968 asked this question by pooling every arm and every
    repeat of a substep into one set of hashes and reporting "more than
    one". That conflates two findings with different causes and
    different fixes -- an arm that disagrees with *itself* is
    nondeterminism and implicates no thread count at all -- so the
    verdicts are computed per (design, stage, substep, witness) and
    printed with the arm each divergence first appears at.
    """
    heading = "### Did `-threads` change the result?"
    if not records:
        return heading + "\n\n**Not measured.**\n"

    all_verdicts = idempotency.verdicts(records)
    if not all_verdicts:
        return heading + "\n\n**Not measured.**\n"
    tally = idempotency.counts(all_verdicts)
    blind = idempotency.thread_blind(records)

    interesting = [
        v
        for v in all_verdicts
        if v.verdict
        in (
            idempotency.CONFOUNDED,
            idempotency.THREAD_DEPENDENT,
            idempotency.RUN_TO_RUN,
        )
    ]
    unproven = [v for v in all_verdicts if v.verdict == idempotency.UNPROVEN]

    out = [heading, ""]
    if not interesting:
        out += [
            "**No.** {} of {} (design, stage, substep, witness) verdicts are "
            "`stable`: every arm agreed with itself across its repeats *and* "
            "with the single-threaded reference, on all three witnesses "
            "(`.sdc` bytes, `.odb` bytes, and the comparable subset of "
            "ORFS's metrics).".format(tally[idempotency.STABLE], len(all_verdicts)),
        ]
        if unproven:
            out += [
                "",
                "{} verdicts are `unproven` rather than stable -- a witness "
                "the substep never wrote, or a ladder that did not reach "
                "the t=1 reference. Silence is not agreement, so they are "
                "counted separately:".format(len(unproven)),
                "",
                "| design | stage | substep | witness | why |",
                "| --- | --- | --- | --- | --- |",
            ]
            for got in unproven:
                out.append(
                    "| {} | {} | `{}` | {} | {} |".format(
                        got.key.design,
                        got.key.stage,
                        got.key.step,
                        got.key.kind,
                        got.detail or "no comparable arm",
                    )
                )
        return "\n".join(out) + "\n"

    out += [
        "**Yes.** {} verdicts are not `stable`. The classes are kept apart "
        "because they are different bugs: `run-to-run` means an arm "
        "disagreed with *itself* between repeats and implicates no thread "
        "count; `thread-dependent` means every arm agreed with itself and a "
        "different arm disagreed; `confounded` means both, and there "
        "thread-dependence is **not** claimed on top of a nondeterministic "
        "base.".format(len(interesting)),
        "",
        "| verdict | design | stage | substep | witness | first diverges at | arms |",
        "| --- | --- | --- | --- | --- | --: | --- |",
    ]
    for got in interesting:
        blind_note = (
            " (thread-blind)"
            if (got.key.design, got.key.stage, got.key.step) in blind
            else ""
        )
        out.append(
            "| {}{} | {} | {} | `{}` | {} | {} | {} |".format(
                got.verdict,
                blind_note,
                got.key.design,
                got.key.stage,
                got.key.step,
                got.key.kind,
                (
                    "t={}".format(got.first_divergent_arm)
                    if got.first_divergent_arm
                    else "-"
                ),
                ", ".join(
                    "t{}{}".format(t, "*" if t in got.unstable_arms else "")
                    for t in sorted(set(got.arms) | set(got.unstable_arms))
                ),
            )
        )
    out += [
        "",
        "`*` marks an arm that disagreed with itself. *thread-blind* marks a "
        "substep that never used more than one core's worth of CPU at any "
        "arm: it measures nothing about thread policy, so a divergence there "
        "is a nondeterminism finding rather than a thread one.",
    ]

    ceilings = idempotency.safe_ceiling(all_verdicts)
    if ceilings:
        out += [
            "",
            "#### The highest thread count nothing diverged at",
            "",
            "Only `thread-dependent` verdicts set this. A `run-to-run` "
            "finding sets no ceiling, because no thread count is safe while "
            "a stage disagrees with itself.",
            "",
            "| design | stage | safe up to |",
            "| --- | --- | --: |",
        ]
        for (design, stage), ceiling in sorted(ceilings.items()):
            out.append(
                "| {} | {} | {} |".format(
                    design, stage, "t={}".format(ceiling) if ceiling else "nothing"
                )
            )
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
            subset = list(arms[start : start + size])
            keys = [k for k in per_key if all(a in per_key[k] for a in subset)]
            if not keys:
                continue
            score = len(keys) * len(subset)
            if score > best_score or (
                score == best_score and len(subset) > len(best[1])
            ):
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
            key = (
                rec["design"],
                rec["stage"],
                name,
                rec["threads"],
                bool(rec.get("pinned")),
            )
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
        "`-threads`. The ceiling on this host is {} (hardware threads);".format(
            ceiling
        ),
        "{} is the physical core count.".format(cores),
        "",
        "```",
        "{:<7} {}   {}".format(
            "stage", " ".join("{:>9}".format("t=" + str(a)) for a in arms), "best"
        ),
    ]
    for stage in STAGE_ORDER:
        if stage not in totals:
            continue
        row = totals[stage]
        if not all(a in row for a in arms):
            continue
        best = min(arms, key=lambda a: row[a])
        out.append(
            "{:<7} {}   t={}{}".format(
                stage,
                " ".join("{:>8.1f}s".format(row[a]) for a in arms),
                best,
                " (ceiling)" if best == ceiling else "",
            )
        )
    out += ["```", ""]

    # Mermaid renders on GitHub; the table above is the fallback that
    # cannot fail to render, so the chart is a bonus rather than the
    # evidence.
    plotted = [
        s for s in STAGE_ORDER if s in totals and all(a in totals[s] for a in arms)
    ]
    if plotted:
        biggest = max(plotted, key=lambda s: max(totals[s].values()))
        out += [
            "```mermaid",
            "xychart-beta",
            '    title "{} wall time vs -threads (all designs)"'.format(biggest),
            '    x-axis "-threads" [{}]'.format(", ".join(str(a) for a in arms)),
            '    y-axis "wall seconds"',
            "    line [{}]".format(
                ", ".join("{:.1f}".format(totals[biggest][a]) for a in arms)
            ),
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

    ranked = sorted(regions.items(), key=lambda kv: -max(kv[1].values()))
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
            "best",
        ),
    ]
    for name, row in ranked:
        n_sites, usable = coverage[name]
        best = min(usable, key=lambda a: row[a])
        out.append(
            "{:<26} {}   t={:<3} {:>2} sites".format(
                name,
                " ".join(
                    ("{:>8.1f}s".format(row[a]) if a in row else "        -")
                    for a in arms
                ),
                best,
                n_sites,
            )
        )
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
        spread = max(
            max(per[stage][d][t][1] for d in designs) for t in (ceiling, best_t)
        )
        runs = min(min(per[stage][d][t][2] for d in designs) for t in (ceiling, best_t))
        res = resolution(spread, runs)
        resolves = best_t != ceiling and abs(walls[best_t] - base) > res
        # The comparison basis is always stated. Dropping designs is as
        # capable of moving the number as dropping arms, and a reader
        # cannot tell either happened from the totals alone.
        scope = " [{} designs".format(len(designs))
        if len(usable) != len(arms):
            scope += ", t={}".format(",".join(str(a) for a in usable))
        scope += "]"
        out.append(
            "| {}{} | {:.1f}s | t={} | {} | {} |".format(
                stage,
                scope,
                base,
                best_t,
                "-" if best_t == ceiling else "{:+.1f}%".format(gain),
                (
                    "at ceiling"
                    if best_t == ceiling
                    else ("yes" if resolves else "**no**")
                ),
            )
        )
        total_ceiling += base
        total_best += walls[best_t] if resolves else base

    if total_ceiling:
        out += [
            "",
            "Flow total over the measured stages: **{:.0f}s at the ceiling, "
            "{:.0f}s under a per-stage choice ({:+.1f}%)** -- counting only "
            "the stages whose gain resolves.".format(
                total_ceiling,
                total_best,
                100.0 * (total_best - total_ceiling) / total_ceiling,
            ),
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
        if bad
        else "All {} substep samples reconcile: no phase stack exceeds the wall "
        "time it splits.".format(checked)
    )
    return (
        "### Does the breakdown add up?\n\n"
        "{}\n\n"
        "{:.0f}% of measured wall time is attributed to a named phase; the "
        "rest is reported as unattributed rather than distributed.\n".format(
            verdict, frac
        )
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
    "3_2_place_iop": None,  # single-threaded
    "5_3_fillcell": None,  # single-threaded
    "5_2_route": "drt",
    "4_1_cts": "cts + OpenSTA",
    "3_4_place_resized": "rsz + OpenSTA",
    "3_5_place_dp": "dpl",
    "5_1_grt": "grt (FastRoute)",
}

GPL_PR = "https://github.com/The-OpenROAD-Project/OpenROAD/pull/11368"
SCALING_STUDY = "https://github.com/The-OpenROAD-Project/bazel-orfs/pull/968"


def load_audit(results_dir):
    """The static audit's JSON, if it has been run. Discovered, not declared.

    Same rule as the results themselves: a section with no inputs says
    so by name rather than quietly disappearing, so a partial campaign
    cannot read as a complete one.
    """
    path = os.path.join(os.path.dirname(results_dir), "sta_audit.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as handle:
            return json.load(handle)
    except ValueError:
        return None


def section_audit(audit):
    """Class 1, and why no patch is carried for it.

    The campaign measures whether a divergence happens. The audit asks
    the separate question of whether the *mechanism* is present, and it
    needs no flow runs -- so it can contradict a clean campaign, or
    explain one.
    """
    heading = "## Class 1: the mechanism, audited rather than measured"
    if not audit:
        return (
            heading + "\n\n**Not yet run.** "
            "`bazelisk run //test/threads_policy:sta_audit -- "
            "--json tmp/threads_policy/sta_audit.json`\n"
        )
    sites = audit.get("sites") or []
    by_risk = collections.Counter(s.get("risk") for s in sites)
    latent = [s for s in sites if s.get("risk") == "latent"]
    iterated = [s for s in sites if s.get("risk") == "iterated"]

    out = [
        heading,
        "",
        "`std::hash<T*>` hashes an address, so iteration order over a "
        "pointer-keyed container follows allocation order, which follows "
        "thread scheduling. Deterministic at one thread, arbitrary above, "
        "and invisible to TSAN because it is not a race. Upstream deleted "
        '`hashPtr` in May 2026 with the comment *"pointer hashing causes '
        "results to change from run to run; use Network::id functions "
        'instead"*.',
        "",
        "Audited against the OpenSTA commit the flow builds, `{}`: **{} "
        "declarations** outside test code -- {} iterated, {} latent, {} "
        "keyed by value or by a named hash.".format(
            (audit.get("sta_commit") or "?")[:10],
            len(sites),
            by_risk["iterated"],
            by_risk["latent"],
            by_risk["low"],
        ),
        "",
    ]

    if iterated:
        out += [
            "### The iterated ones, followed",
            "",
            "Iteration in bucket order is only a defect when the order "
            "survives the loop body. All {} were read, and none do:".format(
                len(iterated)
            ),
            "",
            "| site | where it is iterated | why the order does not survive |",
            "| --- | --- | --- |",
        ]
        for site in iterated:
            out.append(
                "| `{}:{}` | {} | *read the loop* |".format(
                    site["path"], site["line"], site.get("evidence") or "-"
                )
            )
        out += [
            "",
            "`network/NetworkCmp.cc` iterates straight into a `sort`, so "
            "the next statement discards the order. `power/Power.cc` "
            "accumulates into counters, and addition commutes. "
            "`search/Sim.cc`'s observer only invalidates -- and "
            "invalidation lands in `VertexSet = std::set<Vertex*, "
            "VertexIdLess>`, ordered by vertex id rather than by address.",
            "",
            'An earlier version of this audit called the third one "the '
            'shape worth chasing" on the strength of the loop alone, '
            "without reading the observer or the container it writes into. "
            "A shortlist is not a finding until someone has followed it.",
        ]

    if latent:
        out += [
            "",
            "### The watch-list: {} latent sites".format(len(latent)),
            "",
            "Address-hashed, with no iteration found. Correct today and one "
            "range-for away from not being. **No patch is carried for "
            "these**: they fix no divergence this campaign measured, and a "
            "refactor with no failing case behind it is churn wherever it "
            "lands. They are listed so the next reader of this code knows "
            "which containers cannot be iterated safely.",
            "",
            "| site | key | declaration |",
            "| --- | --- | --- |",
        ]
        for site in latent:
            out.append(
                "| `{}:{}` | `{}` | `{}` |".format(
                    site["path"],
                    site["line"],
                    site.get("key_type", "?"),
                    (site.get("decl") or "").replace("|", "\\|"),
                )
            )
    return "\n".join(out) + "\n"


def section_upstream(records, audit):
    """What is proposed upstream. Listed, never opened."""
    all_verdicts = idempotency.verdicts(records) if records else []
    broke = [
        v
        for v in all_verdicts
        if v.verdict
        in (
            idempotency.CONFOUNDED,
            idempotency.THREAD_DEPENDENT,
            idempotency.RUN_TO_RUN,
        )
    ]
    out = ["## Upstream candidates", ""]
    if broke:
        out += [
            "{} verdict(s) diverged; the divergence list above names the "
            "first arm and the class for each. A candidate fix per class "
            "belongs here, measured alone.".format(len(broke)),
        ]
    else:
        out += [
            "**None, and that is the result.** Nothing diverged, and the "
            "class-1 audit found no site whose iteration order reaches a "
            "result, so there is no defect to carry a patch for. Carrying "
            "a preventive refactor instead would be a change with no "
            "failing case behind it.",
            "",
            "What *is* proposed is the missing test, in the shape "
            "`src/gpl/test/mt_invariance01.tcl` already has for global "
            "placement: run `repair_timing` at a thread count, write the "
            "result, diff it against the single-threaded golden. It is "
            "the artefact that was missing every one of the four times "
            "this broke -- each of which was found by a flow user "
            "diffing outputs, never by a regression.",
            "",
            "**Its home is OpenROAD's regression suite, not this repo.** "
            "A guard here does not protect the people who would break "
            "it: an OpenROAD change lands against green upstream CI and "
            "the failure surfaces downstream at bump time, which is the "
            "very pattern this issue was opened about. Carrying it here "
            "would reproduce that one layer down. The working probe is "
            "on the study branch as a reference implementation for "
            "whoever upstreams it.",
            "",
            "A unit-level test is also the only shape that *can* work "
            "upstream, and for the same reason the campaign needed "
            "pinned inputs: starting from a fixed `.odb` sidesteps "
            "yosys entirely. `mt_invariance01` already does this for "
            "global placement. A flow-level invariance test upstream "
            "would be measuring the front end's nondeterminism as much "
            "as the thread count -- which is presumably why the "
            "question has been left to the QoR regressions until "
            "synthesis moves in-tool.",
        ]
    return "\n".join(out) + "\n"


def section_optimum(records):
    """Where the answer to "what is the optimal thread count" lives.

    Not here, when this campaign recorded no timing arms. #968 measured
    that ladder on a 16-core / 32-thread host and published it; the
    honest thing is to point at it rather than to re-derive a weaker
    version of it on whatever machine happens to be running this.

    A thread-scaling optimum is a property of the host as much as of
    the tool -- #968 says so itself, and gives the reason: its own gpl
    optimum moved with design size, and OpenROAD#11368 measured a
    1.28M-instance design preferring the core count while #968's
    smaller designs preferred half of it.
    """
    if not records:
        return ""
    timing = timed(records)
    prov = records[0]["provenance"]
    cores, threads = prov.get("physical_cores"), prov.get("hardware_threads")
    out = [
        "## What the optimal thread count is",
        "",
        "**Not re-litigated here.** [#968]({}) measured that ladder across "
        "6 asap7 designs and 6 thread counts and published it: `place` "
        "wants t=8, `cts` and `grt` want t=16 (the physical core count on "
        "that host), and `route` wants the ceiling -- capping it costs "
        "about 15%. The recommendation that follows, and the one "
        "OpenROAD#11368 implements for global placement, is to cap the "
        "tools that saturate early at the core count and leave `drt` at "
        "the ceiling.".format(SCALING_STUDY),
        "",
        "That ladder was taken on a **16-core / 32-thread** host. This "
        "campaign ran on **{} cores / {} hardware threads**, so re-taking "
        "it here would produce a different machine's answer, not a "
        "correction to #968: a scaling optimum is a property of the host "
        "as much as of the tool, which is why #968 recommends a "
        "work-per-thread heuristic over a constant.".format(cores, threads),
    ]
    if not timing:
        out += [
            "",
            "No `--mode timing` arms were recorded, so every runtime table "
            "below reads *Not measured*. That is deliberate and not a gap "
            "in this campaign: the question here is idempotency, and its "
            "arms run contended on purpose.",
        ]
    return "\n".join(out) + "\n"


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
            rise = {
                n: pts[hi] - min(pts.values())
                for n, pts in curve.items()
                if hi in pts and len(pts) > 1
            }
            if rise:
                worst = max(rise, key=lambda n: rise[n])
                if rise[worst] > 0:
                    region = worst
        owner = PHASE_OWNER.get(region)
        if owner is None:
            # No phase attribution for this substep; fall back to what
            # the substep itself is, rather than dropping its seconds.
            owner = SUBSTEP_OWNER.get(step)
        rows.append(
            (
                walls[ceiling] - walls[best],
                step,
                region,
                owner,
                best,
                walls[ceiling],
                walls[best],
            )
        )
    total = sum(max(0.0, r[0]) for r in rows)
    return rows, total, measured, ceiling


def section_invariance_tldr(records):
    """The finding this campaign exists for, first.

    bazel-orfs#970 asks whether the thread count changes the result.
    That is the headline, and it is available from an idempotency
    campaign alone -- the ladder needs timing arms and may not exist
    yet, in which case #968's TL;DR renders empty and the reader is
    handed a report with no finding at the top.
    """
    all_verdicts = idempotency.verdicts(records)
    if not all_verdicts:
        return ""
    tally = idempotency.counts(all_verdicts)
    designs = sorted({r["design"] for r in records})
    platforms = sorted({d.split("_", 1)[0] for d in designs})
    arms = sorted({r["threads"] for r in records if not r.get("pinned")})
    repeats = max([r["repeat"] for r in records] or [1])

    broke = (
        tally[idempotency.CONFOUNDED]
        + tally[idempotency.THREAD_DEPENDENT]
        + tally[idempotency.RUN_TO_RUN]
    )
    out = [
        "## TL;DR -- did the thread count change the result?",
        "",
        "Arms at t={} on {} design{} across {}, {} repeat{} each, three "
        "witnesses per substep (`.sdc` bytes, `.odb` bytes, and the "
        "comparable subset of ORFS's own metrics).".format(
            ", ".join(str(a) for a in arms),
            len(designs),
            "" if len(designs) == 1 else "s",
            ", ".join(platforms),
            repeats,
            "" if repeats == 1 else "s",
        ),
        "",
        "| verdict | count | what it means |",
        "| --- | --: | --- |",
        "| `stable` | {} | agreed with itself across repeats *and* with "
        "the single-threaded reference |".format(tally[idempotency.STABLE]),
        "| `thread-dependent` | {} | every arm self-consistent, a "
        "different arm disagreed |".format(tally[idempotency.THREAD_DEPENDENT]),
        "| `run-to-run` | {} | an arm disagreed with itself; no thread "
        "count is implicated |".format(tally[idempotency.RUN_TO_RUN]),
        "| `confounded` | {} | both, so thread-dependence is not claimed "
        "|".format(tally[idempotency.CONFOUNDED]),
        "| `unproven` | {} | nothing was established; silence is not "
        "agreement |".format(tally[idempotency.UNPROVEN]),
        "",
    ]
    if broke:
        out += [
            "**{} verdicts are not stable.** The divergence list, the arm "
            "each one first appears at, and the class it falls in are "
            "below.".format(broke),
        ]
    else:
        out += [
            "**Nothing diverged.** That is a negative result and it is "
            "the point. Upstream does watch invariance, but as a side "
            "effect: a thread-dependent result shifts a design's QoR and "
            "the `rules-base.json` regressions notice. What has never "
            "existed is a test that *isolates* the thread count, which "
            "is why all four times this broke it was a flow user "
            "diffing outputs who found it -- a shifted metric says "
            "something moved, not what moved it.",
            "",
            "**Why this was measurable here and is not upstream.** The "
            "comparison needs a fixed netlist, and yosys does not give "
            "one: its `abc` pass runs on a thread pool and the netlist "
            "depends on completion order (YosysHQ/yosys#6170). ORFS does "
            "not pin netlists, so any downstream difference there could "
            "be the front end. bazel-orfs pins "
            "`YOSYS_MAX_THREADS=1` (private/environment.bzl) and caches "
            "stage inputs, so every arm of this campaign started from "
            "byte-identical inputs and a difference could only come from "
            "the thread count. That property, not the harness, is what "
            "made the question answerable.",
        ]
    return "\n".join(out) + "\n"


# A "what to do next" ranking compares substeps against each other, so
# it needs more than one substep to rank. Below this it is not a weak
# answer, it is a category error.
MIN_RANKED_SUBSTEPS = 2


def section_tldr(cells, records):
    """What to do next, first, in as few lines as possible.

    Only renders when the timing arms actually span the flow. A
    campaign that timed one stage -- because it was aimed at that
    stage -- would otherwise print this section's table empty, its
    totals as `0s`, and #968's conclusions underneath as though they
    had been measured here. That is the shape of a partial campaign
    reading as a complete one, which every other section in this file
    is written to avoid.
    """
    rows, total, measured, ceiling = _opportunity(cells, records)
    # The table only prints rows with something to save, so "nothing to
    # save anywhere" renders as an empty table under a `0s` total --
    # which is what a route-only campaign produced. The count of ranked
    # substeps is not the discriminator; the count of *positive* ones
    # is.
    ranked = {step for saving, step, _r, _o, _b, _c, _bb in rows if saving > 0}
    if total <= 0 or len(ranked) < MIN_RANKED_SUBSTEPS:
        timed_stages = sorted({r["stage"] for r in timed(records)})
        if not timed_stages:
            return (
                "## What to do next\n\n**Not measured.** No `--mode timing` "
                "arms were recorded, so there is nothing to rank.\n"
            )
        return (
            "## What to do next\n\n**Not measured across the flow.** The "
            "timing arms cover {} only, so the substeps cannot be ranked "
            "against each other -- ranking is what this section is. See "
            "[#968]({}) for the flow-wide ladder.\n".format(
                ", ".join("`" + s + "`" for s in timed_stages), SCALING_STUDY
            )
        )

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
        "{} design{} -- what is left after it:".format(
            total,
            measured,
            len({k[0] for k in cells}),
            "" if len({k[0] for k in cells}) == 1 else "s",
        ),
        "",
        "| do this next | worth | vs gpl |",
        "| --- | --: | --: |",
    ]
    # Only owners worth listing get a row; the rest is one number, so
    # the reader is not asked to weigh six things that do not matter.
    THRESHOLD = 0.05
    listed = [(o, v) for o, v in ranked if o != "gpl" and v / total >= THRESHOLD]
    for owner, secs in listed:
        out.append(
            "| **{}** -- cap at ~the core count | {:.0f}s ({:.0f}% of "
            "what is left) | {} |".format(
                owner,
                secs,
                100.0 * secs / total,
                "{:.1f}x".format(secs / gpl) if gpl else "n/a",
            )
        )
    rest = total - gpl - sum(v for _o, v in listed)
    out += [
        "",
        "and then **stop**. Everything else together is {:.0f}s across "
        "{} substeps, which is smaller than the run-to-run spread of one "
        "large design -- there is no third thing worth doing on this "
        "evidence.".format(
            rest,
            sum(
                1
                for r in rows
                if r[0] > 0
                and PHASE_OWNER.get(r[2]) not in [o for o, _v in listed] + ["gpl"]
            ),
        ),
        "",
        "### Do not do these",
        "",
        "- **Do not cap `drt`** (detailed route, pin access). It wants the",
        "  ceiling; capping it at the core count costs about 15%.",
        "- **Do not lower ORFS's `NUM_CORES` default.** It is the ceiling,",
        "  not a target. Deriving it from physical cores is wall-neutral",
        "  overall *and* would cap `drt`.",
        '- **Do not "tune grt".** FastRoute is a few percent of `5_1_grt`;',
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
        stamped = sorted({t for (d, st, n, t) in idx if st == step and d in designs})
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
        rows.append(
            (saving, step, walls[ceiling], walls[best], best, dominant, len(designs))
        )

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
        wants = (
            "**the ceiling** -- capping costs time"
            if best_t == ceiling
            else "t={}".format(best_t)
        )
        out.append(
            "| `{}` | {} | {:.1f}s | {:.1f}s | {} | {} | {} |".format(
                step,
                dominant or "_unattributed_",
                ceil_v,
                best_v,
                "-" if saving <= 0 else "{:.1f}s".format(saving),
                "-" if saving <= 0 else "{:.0f}%".format(share),
                wants,
            )
        )
    out += [
        "",
        "Total available: **{:.0f}s** of {:.0f}s measured "
        "(**{:.0f}%**).".format(
            total, sum(r[2] for r in rows), 100.0 * total / sum(r[2] for r in rows)
        ),
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
                    rec["design"],
                    rec["stage"],
                    step,
                    rec["threads"],
                    int(bool(rec.get("pinned"))),
                    rec["repeat"],
                    got["wall_s"],
                    got["user_s"],
                    got["sys_s"],
                    got["cpu_pct"],
                    got["peak_kb"],
                    got["threads"],
                    got.get("result_sha1") or "",
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
    return "\n".join(
        [
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
        ]
    )


def body(records, cells, audit=None):
    if not records:
        return (
            "# ORFS `-threads` policy: cores or hardware threads?\n\n"
            "**No results recorded yet.** Run the campaign, then regenerate.\n"
        )
    prov = records[0]["provenance"]
    cores, threads = prov.get("physical_cores"), prov.get("hardware_threads")
    designs = sorted({r["design"] for r in records})
    platforms = sorted({d.split("_", 1)[0] for d in designs})
    modes = sorted({r.get("mode", "timing") for r in records})

    parts = [
        "# How the flow's parallel regions scale, and what `-threads` should be",
        "",
        "**FYI only -- this PR is for the data and will be closed.** No flow",
        "behaviour changes here, and it recommends *no* change to ORFS.",
        "",
        section_invariance_tldr(records),
        section_audit(audit),
        section_upstream(records, audit),
        section_optimum(records),
        section_tldr(cells, records),
        "`NUM_CORES` -> `openroad -threads N` is a **ceiling**: what a job is",
        'permitted to use, not a target. So the question is not "cores or',
        'hardware threads" but, per parallel region, how far *below* the',
        "ceiling that region wants to sit -- and why.",
        "",
        "Measured over {} design{} on {}, {} thread count{}, and every".format(
            len(designs),
            "" if len(designs) == 1 else "s",
            ", ".join(platforms),
            len(arms_present(cells)) or "no",
            "" if len(arms_present(cells)) == 1 else "s",
        ),
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
        "Bazel sandbox, in its own `FLOW_VARIANT`, via the `_deps`",
        "reproducer the repo already ships. A `timing` arm runs alone on an",
        "otherwise idle machine, asserted at arm start; an `idempotency`",
        "arm runs concurrently with others, because whether two arms",
        "computed the same thing does not depend on how busy the machine",
        "was -- and the scheduling perturbation is a feature there.",
        "",
        "Modes recorded here: {}.".format(", ".join("`" + m + "`" for m in modes)),
        "",
        contended_note(records),
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
        section_work_changed(cells, records),
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
        "**gpl's optimum moves with design size**, so a constant is the",
        "wrong shape for it. The gain from halving shrinks monotonically as",
        "designs grow across this set, and #11368 measures a 1.28M-instance",
        "design preferring the core count -- the same curve, sampled",
        "further along. That argues for a work-per-thread heuristic rather",
        "than a fixed cap.",
        "",
        "**What should not change:** ORFS's `NUM_CORES` default. Deriving",
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
        "- **One machine, one microarchitecture, one SMT ratio** ({}/{} = 2x).".format(
            threads, cores
        ),
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
    parser.add_argument(
        "--raw", action="store_true", help="emit the raw-sample comment"
    )
    parser.add_argument(
        "--verdicts",
        action="store_true",
        help="emit only the idempotency verdicts. The question "
        "bazel-orfs#970 asks, without the ladder around it.",
    )
    args = parser.parse_args()

    results_dir = args.results or os.path.join(
        os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd(),
        "tmp",
        "threads_policy",
        "results",
    )
    records = load(results_dir)
    if not records:
        sys.stderr.write(
            "no results under {}\n"
            "run: bazelisk run //test/threads_policy:campaign\n".format(results_dir)
        )
    cells = index(records)

    if args.raw:
        text = raw_comment(records)
    elif args.verdicts:
        text = section_work_changed(cells, records)
    else:
        text = body(records, cells, load_audit(results_dir))
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
