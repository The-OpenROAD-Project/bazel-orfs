"""The Top's second pass against its first, at the crossings: did making
the cells on the paths over the budget movable (top_level.tcl, TOP_UNFIRM)
move the crossings?

    crossing_verdict.py [--expect moved|nothing]
                        [--sets <firm sets.txt> <final sets.txt>]
                        [--time <firm time dir> <final time dir>]
                        <budget ps> <firm crossing.txt> <final crossing.txt>

The two crossing.txt are crossing_report.py's, each pair of registers once
at its worst: need_ps from to through start end. Line 1 is the verdict,
"moved the crossings" or "DID NOTHING": the second pass did nothing when
under 10 % fewer pairs are over the budget and the worst crossing is less
than 5 % of the budget better. Pairs are counted by name, a floor: a report
names a register by its first and last level of instances.

Then, for information only: with --sets, whether both reports were timed
in the same sets (each pass plans its own, and the pairs are compared by
name either way); the endpoints over the budget in each pass; the pairs by
macro group. --time reads the per-set reports (cross.txt.<n>) of both
passes' crossing_time directories, and adds the paths inside one macro,
and the macros whose paths are in the first pass's reports and in none of
the second's: those were taken out of the timing, not shortened.
--expect stops, exit status 1, when the verdict is not the one given.
A first pass with no pair over the budget has nothing to move: an error;
so is a report without crossing_report.py's header line, an empty file
among them.
"""

import argparse
import collections
import os
import sys

# the first line of crossing_report.py's crossing.txt
CROSSING_HEADER = "# need_ps from_macro to_macro through_macros startpoint endpoint"

# the second pass did nothing when it took fewer than this share of the
# pairs over the budget out and the worst crossing came down by less than
# this share of the budget
FEWER_PCT = 10
BETTER_PCT_OF_BUDGET = 5


def die(message):
    sys.exit("crossing_verdict: " + message)


def open_report(path):
    try:
        return open(path)
    except OSError as e:
        die("%s: %s" % (path, e.strerror))


def read_crossing(path):
    """(start, end) -> (need, from, to, through): crossing_report.py's
    crossing.txt, each pair of registers once at its worst. Its first line
    is the header crossing_report.py always writes: a file without it, an
    empty one among them, is not a report."""
    rows = {}
    number = 0
    with open_report(path) as f:
        for number, line in enumerate(f, 1):
            if number == 1 and line.rstrip("\n") != CROSSING_HEADER:
                die(
                    "%s: not crossing_report.py's crossing.txt: its first line "
                    "is not '%s'" % (path, CROSSING_HEADER)
                )
            fields = line.split()
            if not fields or line.startswith("#"):
                continue
            try:
                if len(fields) != 6:
                    raise ValueError(line)
                need = float(fields[0])
            except ValueError:
                die("%s:%d: not a crossing row: %s" % (path, number, line.rstrip()))
            frm, to, through, start, end = fields[1:]
            key = (start, end)
            if key not in rows or need > rows[key][0]:
                rows[key] = (need, frm, to, through)
    if not number:
        die("%s: not crossing_report.py's crossing.txt: the file is empty" % path)
    return rows


def read_sets(path):
    """crossing_plan.tcl's sets: the blocks of each set, one set per line
    that is neither blank nor a comment."""
    sets = []
    with open_report(path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                sets.append(frozenset(line.split()))
    return sets


def read_inside(d):
    """(start, end) -> (worst need, macro): the rows inside one macro of the
    per-set reports cross.txt.<n> in a crossing_time directory."""
    if not os.path.isdir(d):
        die("%s is not a directory" % d)
    names = sorted(
        n
        for n in os.listdir(d)
        if n.startswith("cross.txt.") and n.rsplit(".", 1)[-1].isdigit()
    )
    if not names:
        die("no cross.txt.<n> in %s" % d)
    rows = {}
    for name in names:
        path = os.path.join(d, name)
        with open_report(path) as f:
            for number, line in enumerate(f, 1):
                fields = line.split()
                if len(fields) < 6 or fields[1] != "inside":
                    continue
                try:
                    need = float(fields[0])
                except ValueError:
                    die("%s:%d: not a row: %s" % (path, number, line.rstrip()))
                key = (fields[4], fields[5])
                if key not in rows or need > rows[key][0]:
                    rows[key] = (need, fields[2])
    return rows


Verdict = collections.namedtuple(
    "Verdict",
    "budget firm_over final_over firm_worst final_worst fewer_pct better moved",
)


def compare(firm, final, budget):
    """The second pass against the first: the pairs over the budget and the
    worst crossing of each (None when a report lists no crossing), and what
    the rule makes of them."""
    firm_over = sum(1 for v in firm.values() if v[0] > budget)
    final_over = sum(1 for v in final.values() if v[0] > budget)
    if not firm_over:
        die(
            "the first pass has no pair over %g ps: nothing for a second pass "
            "to move" % budget
        )
    firm_worst = max(v[0] for v in firm.values())
    final_worst = max((v[0] for v in final.values()), default=None)
    # a report lists no crossing under the budget it was timed at: with none
    # listed the worst is below the budget, which is all there is to compare
    bound = budget if final_worst is None else final_worst
    # needs are written to 0.1 ps: compare what was written, not the sums
    better = round(firm_worst - bound, 6)
    fewer = firm_over - final_over
    need = round(budget * BETTER_PCT_OF_BUDGET / 100.0, 6)
    moved = 100 * fewer >= FEWER_PCT * firm_over or better >= need
    return Verdict(
        budget,
        firm_over,
        final_over,
        firm_worst,
        final_worst,
        100.0 * fewer / firm_over,
        better,
        moved,
    )


def verdict_name(v):
    return "moved the crossings" if v.moved else "DID NOTHING"


def verdict_line(v):
    """Line 1: the verdict, the pairs over the budget and the worst
    crossing of both passes, and the differences."""
    if v.final_worst is None:
        worst = "no crossing listed (firm worst %.1f ps, at least %.1f ps better)" % (
            v.firm_worst,
            v.better,
        )
    else:
        worst = "worst crossing %.1f ps (firm %.1f, %+.1f ps)" % (
            v.final_worst,
            v.firm_worst,
            0.0 - v.better,
        )
    # the change in pairs to 0.1 %, cut toward zero: a share short of the
    # rule's never prints as meeting it (9.997 % fewer is -9.9 %)
    fewer = v.firm_over - v.final_over
    tenths = 1000 * abs(fewer) // v.firm_over
    share = "%s%d.%d %%" % ("-" if fewer > 0 else "+", tenths // 10, tenths % 10)
    return "%s: pairs by name over %g ps: %d (firm %d, %s), %s" % (
        verdict_name(v),
        v.budget,
        v.final_over,
        v.firm_over,
        share,
        worst,
    )


def sets_line(firm, final):
    """Whether both reports were timed in the same sets."""
    if set(firm) == set(final):
        return "sets: the same"
    return "sets: differ (%d firm, %d final)" % (len(firm), len(final))


def endpoints_line(firm, final, budget):
    """The endpoints of the pairs over the budget, by name, in each pass."""
    firm_ends = {k[1] for k, v in firm.items() if v[0] > budget}
    final_ends = {k[1] for k, v in final.items() if v[0] > budget}
    return (
        "endpoints over %g ps: %d (firm %d); %d of the firm's are under now, "
        "%d are new"
        % (
            budget,
            len(final_ends),
            len(firm_ends),
            len(firm_ends - final_ends),
            len(final_ends - firm_ends),
        )
    )


def groups(rows, budget):
    """(from, to, through) -> [pairs over the budget, worst need]."""
    g = {}
    for need, frm, to, through in rows.values():
        if need <= budget:
            continue
        t = g.setdefault((frm, to, through), [0, 0.0])
        t[0] += 1
        t[1] = max(t[1], need)
    return g


def group_table(firm, final, budget):
    firm_g, final_g = groups(firm, budget), groups(final, budget)
    lines = [
        "| from | to | through | firm pairs | firm worst | final pairs | final worst |",
        "|---|---|---|---:|---:|---:|---:|",
    ]

    def size(key):
        return max(firm_g.get(key, [0])[0], final_g.get(key, [0])[0])

    for key in sorted(set(firm_g) | set(final_g), key=lambda k: (-size(k), k)):
        a, b = firm_g.get(key, [0, 0.0]), final_g.get(key, [0, 0.0])
        lines.append("| %s | %s | %s | %d | %.1f | %d | %.1f |" % (key + tuple(a + b)))
    return lines


def inside_over(rows):
    """macro -> {(start, end): need} of the paths inside it."""
    over = {}
    for key, (need, macro) in rows.items():
        over.setdefault(macro, {})[key] = need
    return over


def inside_table(firm_in, final_in, budget):
    """The pairs inside one macro over the budget, per macro."""
    firm_over = inside_over({k: v for k, v in firm_in.items() if v[0] > budget})
    final_over = inside_over({k: v for k, v in final_in.items() if v[0] > budget})
    lines = [
        "paths inside one macro over %g ps, as the sets list them (reported, "
        "not a condition):" % budget,
        "| macro | firm pairs | firm worst | final pairs | final worst "
        "| new in final |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for macro in sorted(set(firm_over) | set(final_over)):
        a, b = firm_over.get(macro, {}), final_over.get(macro, {})
        lines.append(
            "| %s | %d | %.1f | %d | %.1f | %d |"
            % (
                macro,
                len(a),
                max(a.values(), default=0.0),
                len(b),
                max(b.values(), default=0.0),
                sum(1 for key in b if key not in a),
            )
        )
    return lines


def vanished(firm_in, final_in):
    """macro -> (rows, worst need): the macros with paths inside them in
    the first pass's reports and none in the second's, not merely under
    the budget: those paths were taken out of the timing, not shortened."""
    in_final = {v[1] for v in final_in.values()}
    gone = {}
    for need, macro in firm_in.values():
        if macro in in_final:
            continue
        n, w = gone.get(macro, (0, 0.0))
        gone[macro] = (n + 1, max(w, need))
    return gone


def vanished_table(firm_in, final_in):
    gone = vanished(firm_in, final_in)
    lines = [
        "macros whose paths inside them are in the firm pass's sets and in none of "
        "the final pass's (reported, not a condition):"
    ]
    if not gone:
        return lines + ["none"]
    lines += ["| macro | firm rows | firm worst |", "|---|---:|---:|"]
    for macro in sorted(gone):
        lines.append("| %s | %d | %.1f |" % ((macro,) + gone[macro]))
    return lines


def parse(argv):
    p = argparse.ArgumentParser(
        prog="crossing_verdict",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    p.add_argument("--expect", choices=["moved", "nothing"])
    p.add_argument("--sets", nargs=2, metavar=("FIRM_SETS", "FINAL_SETS"))
    p.add_argument("--time", nargs=2, metavar=("FIRM_DIR", "FINAL_DIR"))
    p.add_argument("budget", type=float, metavar="BUDGET_PS")
    p.add_argument("firm", metavar="FIRM_CROSSING_TXT")
    p.add_argument("final", metavar="FINAL_CROSSING_TXT")
    return p.parse_args(argv)


def report(args):
    """The lines of the verdict, and what stops it."""
    firm, final = read_crossing(args.firm), read_crossing(args.final)
    verdict = compare(firm, final, args.budget)
    out = [verdict_line(verdict)]
    if args.sets:
        out.append(sets_line(read_sets(args.sets[0]), read_sets(args.sets[1])))
    out.append(endpoints_line(firm, final, args.budget))
    out += ["", *group_table(firm, final, args.budget)]
    if args.time:
        firm_in, final_in = read_inside(args.time[0]), read_inside(args.time[1])
        out += ["", *inside_table(firm_in, final_in, args.budget)]
        out += ["", *vanished_table(firm_in, final_in)]
    errors = []
    if args.expect and (args.expect == "moved") != verdict.moved:
        errors.append(
            "expected %s, the verdict is %s"
            % (
                "the crossings moved" if args.expect == "moved" else "nothing moved",
                verdict_name(verdict),
            )
        )
    return out, errors


def main(argv):
    out, errors = report(parse(argv))
    print("\n".join(out))
    for e in errors:
        print("crossing_verdict: " + e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
