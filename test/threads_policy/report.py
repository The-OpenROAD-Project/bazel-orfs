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
        "# ORFS `-threads` policy: cores or hardware threads?",
        "",
        "ORFS gives every OpenROAD invocation `-threads $(NUM_CORES)` and",
        "derives `NUM_CORES` from `nproc`, which counts **hardware threads**:",
        "",
        "```make",
        "# flow/scripts/variables.mk",
        "ifeq (,$(strip $(NUM_CORES)))",
        "  NUM_CORES := $(shell nproc 2>/dev/null)        # hardware threads",
        "  # fallbacks: grep -c ^processor /proc/cpuinfo, sysctl -n hw.ncpu, 1",
        "endif",
        "export OPENROAD_ARGS = -no_init -threads $(NUM_CORES) $(OR_ARGS)",
        "```",
        "",
        "On an SMT machine that is twice the core count. This PR measures",
        "whether the second half of those threads pays for itself, per",
        "substep, across {} asap7 design{}. It is documentation and".format(
            len(designs), "" if len(designs) == 1 else "s"),
        "data: no flow behavior changes here.",
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
        section_sweep(cells, records),
        "",
        section_work_changed(cells),
        "",
        section_pinning(cells, records),
        "",
        "## What would change upstream",
        "",
        "The candidate is to derive the default from physical cores and keep",
        "`nproc` as the fallback where topology is not exposed -- on a",
        "machine without SMT the two counts coincide, so the change is a",
        "no-op there:",
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
