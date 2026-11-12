"""The end and start pins of the crossing paths over a budget: what the
Top's second pass takes over from its first (top_level.tcl, TOP_UNFIRM).

    crossing_ends.py <dir of crossing_data.<n>.tsv> <budget ps> <out dir>

crossing_paths.tcl writes crossing_data.<n>.tsv beside each set's report,
one row per crossing path needing more than its data minimum, tab
separated: need_ps, wire_ps, from_macro, to_macro, through_macros (the
macros' names joined with commas, - for none), startpoint, endpoint, the
start's place (x y, - - when it has none) and the end's. Writes
<out dir>/ends.tsv, "group<TAB>end pin<TAB>x y", each end pin once, in the
group (from>to, or from>through>to) of its worst path, and
<out dir>/starts.txt, "start pin<TAB>x y", the start pins of those worst
paths. A report names a register by its first and last level of
instances, so two registers can share a name: a pin is its name and its
place. Stops, with one line saying which, when the directory holds no
crossing data or no crossing needs more than the budget: there is nothing
to unfirm and the first pass is the result.
"""

import glob
import os
import sys

COLUMNS = 9


def read_rows(path):
    """The rows of one crossing_data file, (need, group, start, end), a pin
    being (name, place)."""
    rows = []
    with open(path) as f:
        for number, line in enumerate(f, 1):
            if line.startswith("#") or not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) != COLUMNS:
                sys.exit(
                    "crossing_ends: %s:%d: %d tab-separated columns, not %d"
                    % (path, number, len(fields), COLUMNS)
                )
            need, _wire, frm, to, through, start, end, start_at, end_at = fields
            via = [m for m in through.split(",") if m not in ("", "-")]
            rows.append(
                (
                    float(need),
                    ">".join([frm] + via + [to]),
                    (start, start_at),
                    (end, end_at),
                )
            )
    return rows


def rank(need, group, start):
    """Smaller is worse: the larger need first, then the smaller names."""
    return (-need, group, start)


def worst_paths(rows, budget):
    """end -> (need, group, start): each end pin once, at its worst path
    over the budget. Equal needs go to the smaller group and start, so the
    answer does not depend on the order of the rows."""
    worst = {}
    for need, group, start, end in rows:
        if need <= budget:
            continue
        if end not in worst or rank(need, group, start) < rank(*worst[end]):
            worst[end] = (need, group, start)
    return worst


def ends_text(worst):
    """ends.tsv: group, end pin, its place; sorted by end."""
    return "".join(
        "%s\t%s\t%s\n" % (worst[end][1], end[0], end[1]) for end in sorted(worst)
    )


def starts_text(worst):
    """starts.txt: start pin, its place; each start once, sorted."""
    return "".join(
        "%s\t%s\n" % start for start in sorted({w[2] for w in worst.values()})
    )


def summary(worst, rows_over, budget):
    """The count of rows, end pins and start pins, then a line per group,
    the one with the most ends first."""
    starts = {w[2] for w in worst.values()}
    by = {}
    for need, group, _start in worst.values():
        n, w = by.get(group, (0, 0.0))
        by[group] = (n + 1, max(w, need))
    lines = [
        "crossing_ends: %d rows over %g ps, %d end pins (%d names), "
        "%d start pins (%d names)"
        % (
            rows_over,
            budget,
            len(worst),
            len({e[0] for e in worst}),
            len(starts),
            len({s[0] for s in starts}),
        )
    ]
    for group in sorted(by, key=lambda g: (-by[g][0], g)):
        lines.append(
            "  %-45s %6d ends, worst %.1f ps" % (group, by[group][0], by[group][1])
        )
    return lines


def main(argv):
    if len(argv) != 4:
        sys.exit(__doc__)
    src, out = argv[1], argv[3]
    try:
        budget = float(argv[2])
    except ValueError:
        sys.exit("crossing_ends: the budget is not a number: %s" % argv[2])
    names = sorted(glob.glob(os.path.join(src, "crossing_data.*.tsv")))
    if not names:
        sys.exit(
            "crossing_ends: no crossing_data.<n>.tsv in %s: the crossings were "
            "timed without crossing data (crossing_data_min_ps), nothing to "
            "unfirm" % src
        )
    rows = []
    for name in names:
        rows += read_rows(name)
    worst = worst_paths(rows, budget)
    if not worst:
        sys.exit(
            "crossing_ends: no crossing over %g ps: nothing to unfirm; the "
            "firm Top is the result" % budget
        )
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "ends.tsv"), "w") as f:
        f.write(ends_text(worst))
    with open(os.path.join(out, "starts.txt"), "w") as f:
        f.write(starts_text(worst))
    rows_over = sum(1 for row in rows if row[0] > budget)
    print("\n".join(summary(worst, rows_over, budget)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
