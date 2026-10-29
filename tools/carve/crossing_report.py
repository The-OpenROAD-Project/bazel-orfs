"""The crossing report of a parent macro's top level, merged from the sets
it was timed in (top_level.tcl, CROSSING_SETS): every register-to-register
path whose start and end are in different macros, once, its need the
same in every set that timed it, then a table per macro pair and per end
macro and a histogram of the need.

    crossing_report.py [--whole <crossing.txt>] <out_dir> <budget_ps> <crossing.txt.N>...

Writes <out_dir>/crossing.txt (worst first), tables.md and histogram.svg.
A directory among the reports stands for its cross.txt.* (a Bazel run's
output directory). --whole: the same design timed whole, in one process;
the merged sets must hold its crossing paths, each needing the same time,
or the report stops (the method's check, on a design small enough to time
whole).
"""

import os
import sys

BIN_PS = 50


def read(paths):
    """Each set's paths, (start, end) -> (need, from, to); the same path
    from two sets must need the same time, or the sets disagree."""
    merged = {}
    for path in paths:
        # one set can list a start and end twice (a transition or a path
        # group apart): its worst is the set's
        mine = {}
        with open(path) as f:
            for line in f:
                fields = line.split()
                if len(fields) not in (6, 7) or fields[1] != "crossing":
                    continue
                need, _, frm, to, start, end = fields[:6]
                through = fields[6] if len(fields) == 7 else "-"
                key = (start, end)
                value = (float(need), frm, to, through)
                if key not in mine or value[0] > mine[key][0]:
                    mine[key] = value
        for key, value in mine.items():
            if key in merged and abs(merged[key][0] - value[0]) > 0.05:
                sys.exit(
                    "crossing_report: %s -> %s needs %.1f in one set, %.1f in another"
                    % (key[0], key[1], merged[key][0], value[0])
                )
            merged[key] = value
    return merged


def compare(merged, whole):
    """What the sets and the whole design disagree on: a path one lacks,
    or a need more than 0.05 ps apart."""
    diffs = []
    for key in sorted(set(merged) | set(whole)):
        if key not in merged:
            diffs.append("%s -> %s: only timed whole" % key)
        elif key not in whole:
            diffs.append("%s -> %s: only in the sets" % key)
        elif abs(merged[key][0] - whole[key][0]) > 0.05:
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


def main(out_dir, budget, paths, whole=None):
    merged = read(expand(paths))
    if whole is not None:
        diffs = compare(merged, read([whole]))
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
    if len(args) < 3:
        sys.exit(__doc__)
    main(args[0], float(args[1]), args[2:], whole)
