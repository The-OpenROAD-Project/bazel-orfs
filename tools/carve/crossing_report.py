"""The crossing report of a parent macro's top level, merged from the sets
it was timed in (top_level.tcl, CROSSING_SETS): the register-to-register
paths the sets list that start and end in different macros, or pass
through another one, each pair of registers once at its worst over the
sets, every set that holds its blocks accounting for it, then a table per
macro pair and per end macro and a histogram of the need. A set lists the
worst paths into an endpoint, not every path into it (crossing_paths.tcl,
-endpoint_path_count 1; a pair of registers can still be listed more than
once, at its worst and lower): the paths counted are close to the
endpoints over the budget, and a floor on the pairs of registers over it.

    crossing_report.py [--whole <crossing.txt>] <out_dir> <budget_ps> <sets.txt> <crossing.txt.N>...

<sets.txt> is crossing_plan.tcl's, the blocks of each set. Set N's report
is the one whose name ends in .N (crossing_time_sets.tcl), and every set
has one. Writes <out_dir>/crossing.txt (worst first), tables.md and
histogram.svg. A directory among the reports stands for its cross.txt.*
(a Bazel run's output directory). --whole: the same design timed whole, in
one process; the merged sets must hold its crossing paths, each needing
the same time, or the report stops (the method's check, on a design small
enough to time whole).
"""

import os
import sys

# crossing_paths.tcl writes each need to 0.1 ps, so two sets that agree
# can print 0.1 apart: the sets and the whole design must agree to the
# digit they are written to
TOL_PS = 0.1 + 1e-6

BIN_PS = 50


def read_sets(path):
    """crossing_plan.tcl's sets, the blocks of each: the N-th line that is
    neither blank nor a comment is set N, a comment being a line that
    starts with #, as crossing_time_sets.tcl numbers them."""
    sets = []
    with open(path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                sets.append(frozenset(line.split()))
    return sets


def read_report(path):
    """One report's crossing paths, (start, end, through) -> (need, from,
    to), and each endpoint's worst need over every row listed into it, a
    path inside one macro too. A report can list a path more than once:
    its worst is the report's. crossing_paths.tcl ends a report with the
    count of its crossing rows and of its inside rows; a line that is
    neither a comment, a row nor a count stops the report, and so do
    counts that are not the rows read: a report cut short would otherwise
    read as one with fewer paths."""
    crossing, ends = {}, {}
    rows = {"crossing": 0, "inside": 0}
    counts = {}
    with open(path) as f:
        for line in f:
            fields = line.split()
            if not fields or line.startswith("#"):
                continue
            if len(fields) == 2 and fields[0] in rows and fields[1].isdigit():
                counts[fields[0]] = int(fields[1])
                continue
            if len(fields) not in (6, 7, 8) or fields[1] not in rows:
                sys.exit(
                    "crossing_report: %s: neither a row nor a count: %s"
                    % (path, line.rstrip())
                )
            need, kind, frm, to, start, end = fields[:6]
            need = float(need)
            through = fields[6] if len(fields) >= 7 else "-"
            rows[kind] += 1
            if need > ends.get(end, 0.0):
                ends[end] = need
            if kind != "crossing":
                continue
            key = (start, end, through)
            if key not in crossing or need > crossing[key][0]:
                crossing[key] = (need, frm, to)
    if counts != rows:
        sys.exit(
            "crossing_report: %s has %d crossing and %d inside rows, and it "
            "ends counting %s: cut short, or not a report"
            % (
                path,
                rows["crossing"],
                rows["inside"],
                " and ".join("%d %s" % (counts[k], k) for k in sorted(counts))
                or "none",
            )
        )
    return crossing, ends


def read(sets_path, paths):
    """The sets and the report of each, in the sets' order."""
    sets = read_sets(sets_path)
    reports = [None] * len(sets)
    for path in expand(paths):
        suffix = path.rsplit(".", 1)[-1]
        if not suffix.isdigit() or int(suffix) >= len(sets):
            sys.exit(
                "crossing_report: %s is the report of none of the %d sets in %s"
                % (path, len(sets), sets_path)
            )
        n = int(suffix)
        if reports[n] is not None:
            sys.exit("crossing_report: %s: set %d has two reports" % (path, n))
        reports[n] = read_report(path)
    for n, report in enumerate(reports):
        if report is None:
            sys.exit("crossing_report: %s has no report" % name(sets, n))
    return sets, reports


def name(sets, n):
    return "set %d (%s)" % (n, " ".join(sorted(sets[n])))


def check(sets, reports, budget):
    """Stops unless the sets agree on every crossing path. A path is a
    start, an end and the macros passed between them: two registers can be
    joined directly and through a third block (XSTile run 27: MemBlock's
    s2Valid into a parent register, 3,411.8 ps through Flt and 2,437.6 ps
    directly), and only a set holding that block times the path through
    it. A set times a path when it holds every block the path touches
    (crossing_cones.tcl); the parent, named by no set, is in every one.
    What the check relies on: at an endpoint, the worst path a set timed
    is among the rows it writes, unless that path starts at a port
    (crossing_paths.tcl, -endpoint_path_count 1). So a set that timed a
    path lists it at its worst over the sets, or lists a path into the
    same endpoint needing at least as much: from any start, a path inside
    one macro too. A set that holds a path's blocks, or lists the path,
    and shows nothing that bad into its endpoint is the sets disagreeing.
    A set that lists a path without holding its blocks timed it across
    its cut (crossing_cones keeps a register right on a crossing net, and
    a short feedthrough without its side inputs) and can list it lower
    for that: such a stop is the cut, not the timing. XSTile run 27's
    nine sets list no such path.
    A path whose blocks no set holds is the plan and the reports
    disagreeing: crossing_plan.tcl plans a set for the blocks of every
    path. A path that touches no block, from the parent to the parent
    through a cell of the top level, is owed by no set: every set's cones
    cross the top level, and a net to a top-level cell is the seed of
    none, so only the sets that list it answer for it. A path within a
    written digit of the budget can be under it in another set, unlisted.
    A path from a top-level port is not listed: where it shares a path
    group with the registers' paths into its endpoint (asap7's
    constraints.sdc gives in2reg and reg2reg a group each), one that
    pushed a crossing out cannot be seen here, and stops the report as a
    disagreement would."""
    blocks = frozenset().union(*sets)
    # each path's worst need, and the set that lists it there
    worst = {}
    for n, (crossing, _) in enumerate(reports):
        for key, (need, frm, to) in crossing.items():
            if key not in worst or need > worst[key][0]:
                worst[key] = (need, frm, to, n)
    for key, (need, frm, to, at) in sorted(
        worst.items(), key=lambda kv: (-kv[1][0], kv[0])
    ):
        start, end, through = key
        touched = ({frm, to} | set(through.split(","))) & blocks
        if touched and not any(touched <= held for held in sets):
            sys.exit(
                "crossing_report: %s -> %s through %s, %.1f ps in %s: no set "
                "holds its blocks (%s)"
                % (
                    start,
                    end,
                    through,
                    need,
                    name(sets, at),
                    " ".join(sorted(touched)),
                )
            )
        for n, (crossing, ends) in enumerate(reports):
            listed = key in crossing
            owed = bool(touched) and touched <= sets[n]
            if n == at or not (listed or owed):
                continue
            if not listed and need < budget + TOL_PS:
                continue
            if ends.get(end, 0.0) >= need - TOL_PS:
                continue
            sys.exit(
                "crossing_report: %s -> %s through %s needs %.1f ps in %s; %s %s, and %s"
                % (
                    start,
                    end,
                    through,
                    need,
                    name(sets, at),
                    name(sets, n),
                    (
                        "lists it at %.1f ps" % crossing[key][0]
                        if listed
                        else "holds its blocks and does not list it"
                    ),
                    (
                        "the worst path it lists into that endpoint needs %.1f ps"
                        % ends[end]
                        if end in ends
                        else "it lists no path into that endpoint"
                    ),
                )
            )


def merge(reports):
    """(start, end) -> (need, from, to, through): each pair of registers
    once, at the worst of its paths over the reports, with the macros that
    one passes."""
    merged = {}
    for crossing, _ in reports:
        for (start, end, through), (need, frm, to) in crossing.items():
            key = (start, end)
            if key not in merged or need > merged[key][0]:
                merged[key] = (need, frm, to, through)
    return merged


def compare(merged, whole):
    """What the sets and the whole design disagree on: a path one lacks,
    or a need more than one written digit (0.1 ps) apart."""
    diffs = []
    for key in sorted(set(merged) | set(whole)):
        if key not in merged:
            diffs.append("%s -> %s: only timed whole" % key)
        elif key not in whole:
            diffs.append("%s -> %s: only in the sets" % key)
        elif abs(merged[key][0] - whole[key][0]) > TOL_PS:
            diffs.append(
                "%s -> %s: %.1f ps in the sets, %.1f ps whole"
                % (key[0], key[1], merged[key][0], whole[key][0])
            )
    return diffs


def expand(paths):
    """A directory stands for the sets' reports in it."""
    out = []
    for path in paths:
        if os.path.isdir(path):
            out.extend(
                sorted(
                    os.path.join(path, n)
                    for n in os.listdir(path)
                    if n.startswith("cross.txt.")
                )
            )
        else:
            out.append(path)
    return out


def histogram(needs, budget):
    """Bins of BIN_PS from the lowest need, (low, count)."""
    if not needs:
        return []
    low = int(min(needs) // BIN_PS) * BIN_PS
    high = int(max(needs) // BIN_PS) * BIN_PS
    counts = {b: 0 for b in range(low, high + BIN_PS, BIN_PS)}
    for n in needs:
        counts[int(n // BIN_PS) * BIN_PS] += 1
    return sorted(counts.items())


def svg(bins, budget, title):
    """A bar chart, the budget as a line; tokens, so it reads in both themes."""
    width, height, pad = 720, 300, 44
    if not bins:
        return "<svg xmlns='http://www.w3.org/2000/svg'/>"
    top = max(c for _, c in bins)
    x0, x1 = bins[0][0], bins[-1][0] + BIN_PS
    sx = (width - 2 * pad) / (x1 - x0)
    sy = (height - 2 * pad) / top
    out = [
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 %d %d' role='img' aria-label='%s'>"
        % (width, height, title),
        "<style>text{font:12px sans-serif;fill:currentColor}</style>",
    ]
    for low, count in bins:
        x = pad + (low - x0) * sx
        h = count * sy
        over = low >= budget
        out.append(
            "<rect x='%.1f' y='%.1f' width='%.1f' height='%.1f' fill='%s'/>"
            % (
                x,
                height - pad - h,
                BIN_PS * sx - 1,
                h,
                "#c0392b" if over else "#7f8c8d",
            )
        )
    bx = pad + (budget - x0) * sx
    if x0 <= budget <= x1:
        out.append(
            "<line x1='%.1f' y1='%d' x2='%.1f' y2='%d' stroke='currentColor' stroke-dasharray='4 3'/>"
            % (bx, pad - 10, bx, height - pad)
        )
        out.append("<text x='%.1f' y='%d'>%d ps</text>" % (bx + 4, pad - 12, budget))
    out.append("<text x='%d' y='%d'>%d ps</text>" % (pad, height - pad + 18, x0))
    out.append(
        "<text x='%d' y='%d' text-anchor='end'>%d ps</text>"
        % (width - pad, height - pad + 18, x1)
    )
    out.append("<text x='%d' y='%d'>%d paths</text>" % (4, pad - 12, top))
    out.append("</svg>")
    return "\n".join(out)


def main(out_dir, budget, sets_path, paths, whole=None):
    sets, reports = read(sets_path, paths)
    check(sets, reports, budget)
    merged = merge(reports)
    if whole is not None:
        diffs = compare(merged, merge([read_report(whole)]))
        if diffs:
            sys.exit(
                "crossing_report: the sets and the whole design disagree:\n"
                + "\n".join(diffs)
            )
    os.makedirs(out_dir, exist_ok=True)
    rows = sorted(merged.items(), key=lambda kv: -kv[1][0])
    with open(os.path.join(out_dir, "crossing.txt"), "w") as f:
        f.write("# need_ps from_macro to_macro through_macros startpoint endpoint\n")
        for (start, end), (need, frm, to, through) in rows:
            f.write("%.1f %s %s %s %s %s\n" % (need, frm, to, through, start, end))

    over = [(k, v) for k, v in rows if v[0] > budget]
    pairs, starts, ends, throughs = {}, {}, {}, {}

    def count(table, key, need):
        t = table.setdefault(key, [0, 0.0])
        t[0] += 1
        t[1] = max(t[1], need)

    for _, (need, frm, to, through) in over:
        count(pairs, (frm, to, through), need)
        count(starts, frm, need)
        count(ends, to, need)
        for m in through.split(",") if through != "-" else []:
            count(throughs, m, need)
    bins = histogram([v[0] for _, v in rows], budget)
    with open(os.path.join(out_dir, "tables.md"), "w") as f:
        f.write(
            "%d crossing paths timed, %d over %d ps\n\n"
            % (len(rows), len(over), budget)
        )
        f.write(
            "| from | to | through | paths over | worst ps |\n|---|---|---|---:|---:|\n"
        )
        for (frm, to, through), (n, worst) in sorted(
            pairs.items(), key=lambda kv: -kv[1][0]
        ):
            f.write("| %s | %s | %s | %d | %.1f |\n" % (frm, to, through, n, worst))
        for title, table in (
            ("starts in", starts),
            ("ends in", ends),
            ("passes through", throughs),
        ):
            f.write("\n| %s | paths over | worst ps |\n|---|---:|---:|\n" % title)
            for m, (n, worst) in sorted(table.items(), key=lambda kv: -kv[1][0]):
                f.write("| %s | %d | %.1f |\n" % (m, n, worst))
        f.write("\n| need ps | paths |\n|---|---:|\n")
        for low, count in bins:
            f.write("| %d-%d | %d |\n" % (low, low + BIN_PS, count))
    with open(os.path.join(out_dir, "histogram.svg"), "w") as f:
        f.write(svg(bins, budget, "crossing paths by need, budget %d ps" % budget))
    print(
        "crossing_report: %d crossing paths timed, %d over %d ps, %d macro pairs"
        % (len(rows), len(over), budget, len(pairs))
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    whole = None
    if args[:1] == ["--whole"]:
        whole, args = args[1], args[2:]
    if len(args) < 4:
        sys.exit(__doc__)
    main(args[0], float(args[1]), args[2], args[3:], whole)
