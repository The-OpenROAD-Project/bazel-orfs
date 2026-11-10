"""The crossing ledger checked against the top level it stands in for.

    crossing_ledger_check.py --top <top.txt> --hub <ledger> --block <M>=<ledger>...
        [--max-skew <ps>] [--zero <part>] [--zero-half] [--drop <M>]
        [--spot] [--miss]
    crossing_ledger_check.py --same <ledger> <ledger>
    crossing_ledger_check.py --pairs <ledger> <pairs.txt>

<top.txt> is crossing_ledger_top.tcl's: the register-to-register paths
the routed top level times through each crossing net, each with the
period it needs (need), and that with its clock taken out (free): the
path, launching clock pin to capturing register. The ledger
(crossing_ledger.py) holds for a net the longest path through it,
summed from halves read in parts that never saw each other, so:

  - no path through a net is longer than the ledger holds for the net;
  - the net's slowest path is as long as the ledger holds;
  - the ledger has a row for the nets the top level times a path
    through, and for no other;
  - no path's clock adds more than --max-skew to it: the ledger holds no
    clock, and says nothing of a top level whose clock tree is broken.

The first two within the tolerance, the larger of 20 ps and 10 % of the
path: a part does not see the slew that arrives at its inputs or the
load its outputs drive.

The period a net needs is its path and what the top level's clock adds
between the two registers, which no part sees and no ledger holds. How
far the ledger is from that period is not checked; it is counted and
printed (`as a period`), the nets outside the same tolerance and on
which side, for whoever reads a ledger's path as a period.

--zero <part> (hub, or a block), --zero-half and --drop <M> are the
negative controls: the check with that part's halves all zero, with one
half zero (the launch into the net the top level's slowest path runs
through), or without that block's ledger. Each must fail.

--spot: the hub's ledger checked a pin of each direction with two or
more registers of different delay behind it against a path search, and
holds the slowest (`# spot` lines). --miss: its `# miss` lines count the
pins its own halves put over the boundary budgets, some pin is over, and
the ledger was written all the same.

--same: two ledgers of one part, read under different boundary
constraints, hold the same halves.

--pairs: a ledger's feed-throughs against <pairs.txt>, `pair <in> <out>
<d> <d zero>` for every input and output a direct search from the one to
the other times a path between: the ledger's arcs are those pairs, each
with the delay of the pair's slowest path, within the fuzz of a delay
read 100,000 ps from zero.
"""

import argparse
import os
import sys
import tempfile

import crossing_ledger
from crossing_ledger import LedgerError

TOLERANCE_PS = 20.0
TOLERANCE_OF_PATH = 0.10
# two readings of one half
SAME_PS = 0.1
# a delay the ledger reads 100,000 ps from zero against one read near it:
# twice OpenSTA's fuzzy equal there (crossing_ledger.tcl's ledger_fuzz)
FUZZ_PS = 0.2
# a number printed with two decimals
PRINTED_PS = 0.005


def tolerance(free):
    return max(TOLERANCE_PS, TOLERANCE_OF_PATH * free)


def read_top(path):
    """The top level's paths by crossing net, {net: [{need, free, clock,
    ends}]}, the nets with none among them."""
    paths = {}
    with open(path) as f:
        for n, line in enumerate(f, 1):
            where = "%s:%d" % (path, n)
            fields = line.split()
            if not fields or fields[0] == "#":
                continue
            if fields[0] == "path" and len(fields) == 7:
                paths.setdefault(fields[1], []).append(
                    {
                        "need": crossing_ledger.number(fields[2], where),
                        "free": crossing_ledger.number(fields[3], where),
                        "clock": crossing_ledger.number(fields[4], where),
                        "ends": "%s to %s" % (fields[5], fields[6]),
                    }
                )
            elif fields[0] == "none" and len(fields) == 2:
                paths.setdefault(fields[1], [])
            else:
                raise LedgerError("%s: not a path: %s" % (where, line.strip()))
    return paths


def check(rows, paths, max_skew):
    """(errors, lines): where the ledger and the top level disagree, and
    how far apart they are where they agree."""
    path = {r["net"]: r["path"] for r in rows}
    timed = {net: got for net, got in paths.items() if got}
    errors = []
    lost = sorted(set(path) - set(timed))
    if lost:
        errors.append(
            "the top level times no path through %d nets the ledger has a row for: %s"
            % (len(lost), crossing_ledger.some(lost))
        )
    blind = sorted(set(timed) - set(path))
    if blind:
        errors.append(
            "the ledger has no row for %d nets the top level times a path through: %s"
            % (len(blind), crossing_ledger.some(blind))
        )
    under = []
    over = []
    apart = []
    clock = []
    for net in sorted(set(timed) & set(path)):
        for p in timed[net]:
            clock.append((p["clock"], net, p))
            short = p["free"] - path[net]
            if short > tolerance(p["free"]):
                under.append((short, net, p))
        worst = max(p["free"] for p in timed[net])
        apart.append((path[net] - worst, net, worst))
        if path[net] - worst > tolerance(worst):
            over.append((path[net] - worst, net, worst))
    if under:
        under.sort(key=lambda u: (-u[0], u[1]))
        errors.append(
            "ledger under the top level: %d paths through %d nets are longer than "
            "the net's halves sum to, by more than the tolerance: %s"
            % (
                len(under),
                len(set(net for _, net, _ in under)),
                crossing_ledger.some(
                    [
                        "%s %.1f against %.1f ps (%s);"
                        % (net, path[net], p["free"], p["ends"])
                        for _, net, p in under
                    ],
                    5,
                ),
            )
        )
    if over:
        over.sort(key=lambda o: (-o[0], o[1]))
        errors.append(
            "ledger over the top level: on %d nets the halves sum to more than the "
            "slowest path through the net, by more than the tolerance: %s"
            % (
                len(over),
                crossing_ledger.some(
                    [
                        "%s %.1f against %.1f ps;" % (net, path[net], worst)
                        for _, net, worst in over
                    ],
                    5,
                ),
            )
        )
    lines = [
        "crossing ledger against the top level: %d nets, %d paths, "
        "tolerance the larger of %g ps and %g %% of the path"
        % (len(apart), len(clock), TOLERANCE_PS, 100 * TOLERANCE_OF_PATH)
    ]
    if apart:
        size = sorted(abs(e) for e, _, _ in apart)
        mean = sum(e for e, _, _ in apart) / len(apart)
        far = max(apart, key=lambda a: abs(a[0]))
        rel = max(apart, key=lambda a: abs(a[0]) / a[2])
        lines += [
            "ledger less top level, each net's slowest path: mean %.2f ps, "
            "90 %% of the nets within %.2f ps" % (mean, size[(len(size) * 9) // 10]),
            "worst %.2f ps: %s, %.1f against %.1f ps"
            % (far[0], far[1], path[far[1]], far[2]),
            "worst of its path %.2f %%: %s, %.1f against %.1f ps"
            % (100 * rel[0] / rel[2], rel[1], path[rel[1]], rel[2]),
        ]
        if mean < -TOLERANCE_PS / 2:
            lines.append(
                "WARNING: the ledger reads %.1f ps under the top level on average: "
                "the slew at the parts' inputs and the load on their outputs, which "
                "no part sees, are the first to look at" % -mean
            )
    if clock:
        lines.append(
            "the top level's clock adds %.2f to %.2f ps to a path, limit %g"
            % (min(c[0] for c in clock), max(c[0] for c in clock), max_skew)
        )
        lines += period(path, timed)
        skewed = max(clock, key=lambda c: abs(c[0]))
        if abs(skewed[0]) > max_skew:
            errors.append(
                "the top level's clock adds %.1f ps to a path through %s (%s), over "
                "the %g ps the ledger is checked within"
                % (skewed[0], skewed[1], skewed[2]["ends"], max_skew)
            )
    return errors, lines


def period(path, timed):
    """The lines: how far the ledger's paths are from the periods the top
    level needs, its clock in. Not a check: a path holds no clock."""
    apart = []
    for net in sorted(set(timed) & set(path)):
        most = max(p["need"] for p in timed[net])
        apart.append((path[net] - most, net, most))
    out = [a for a in apart if abs(a[0]) > tolerance(a[2])]
    far = max(apart, key=lambda a: abs(a[0]))
    lines = [
        "as a period, the top level's clock in, which no ledger holds: %d of %d "
        "nets outside the tolerance, %d of them with the ledger under"
        % (len(out), len(apart), sum(1 for a in out if a[0] < 0)),
        "as a period, ledger less top level: mean %.2f ps, %.2f to %.2f ps, "
        "worst %s, %.1f against %.1f ps"
        % (
            sum(a[0] for a in apart) / len(apart),
            min(apart)[0],
            max(apart)[0],
            far[1],
            path[far[1]],
            far[2],
        ),
    ]
    slowest = max(apart, key=lambda a: a[2])
    lines.append(
        "as a period, the slowest crossing: %s, the top level needs %.1f ps, "
        "the ledger's path %.1f; the ledger's longest path %.1f"
        % (slowest[1], slowest[2], path[slowest[1]], max(path.values()))
    )
    return lines


def halves(path):
    """A ledger's numbers by line, {(kind, pin...): [ps or None]}: an
    out's launch and slowest feed-through, an in's capture and slowest
    feed-through (feed), an arc's delay, each as routed and at zero
    wire."""
    got = {}
    with open(path) as f:
        for n, line in enumerate(f, 1):
            where = "%s:%d" % (path, n)
            fields = line.split()
            if not fields or fields[0] == "#":
                continue
            if fields[0] == "out" and len(fields) == 8:
                key, values = ("out", fields[1]), fields[2:6]
            elif fields[0] == "in" and len(fields) == 5:
                key, values = ("in", fields[1]), fields[2:4]
            elif fields[0] == "feed" and len(fields) == 4:
                key, values = ("feed", fields[1]), fields[2:4]
            elif fields[0] == "arc" and len(fields) == 5:
                key, values = ("arc", fields[1], fields[2]), fields[3:5]
            else:
                raise LedgerError("%s: not a ledger line: %s" % (where, line.strip()))
            got[key] = [crossing_ledger.number(v, where) for v in values]
    return got


def comments(path, kind):
    """A ledger's `# <kind>` lines, their fields."""
    with open(path) as f:
        return [l.split()[2:] for l in f if l.split()[:2] == ["#", kind]]


def zeroed(path, out):
    """The ledger at path written to out with every half zero: the part
    as if nothing in it took any time."""
    spans = {"out": (2, 6), "in": (2, 4), "feed": (2, 4), "arc": (3, 5)}
    with open(path) as f, open(out, "w") as g:
        for line in f:
            fields = line.split()
            if fields and fields[0] in spans:
                a, b = spans[fields[0]]
                fields[a:b] = ["-" if v == "-" else "0.00" for v in fields[a:b]]
                line = " ".join(fields) + "\n"
            g.write(line)
    return out


def half_zeroed(paths, parts, out):
    """(part, pin, net): one of the ledgers in parts, {part: path},
    written to out with one half zero: the launch into the net the top
    level's slowest path runs through, of those a register launches
    into."""
    read = {name: crossing_ledger.read_part(name, p) for name, p in parts.items()}
    hub = read.pop(crossing_ledger.HUB)
    nets, _, _ = crossing_ledger.connect(hub, read)
    read[crossing_ledger.HUB] = hub
    slow = sorted(
        ((max(p["free"] for p in got), net) for net, got in paths.items() if got),
        reverse=True,
    )
    for _, net in slow:
        if net not in nets:
            continue
        name, pin = nets[net][0]
        if read[name]["outs"][pin][0] is None:
            continue
        with open(parts[name]) as f, open(out, "w") as g:
            for line in f:
                fields = line.split()
                if fields[:2] == ["out", pin]:
                    fields[2:4] = ["0.00", "0.00"]
                    line = " ".join(fields) + "\n"
                g.write(line)
        return name, pin, net
    raise LedgerError("no net the top level times a path through has a launch half")


def same(a, b):
    """The errors: where two ledgers of one part differ."""
    ha, hb = halves(a), halves(b)
    errors = []
    for key in sorted(set(ha) ^ set(hb)):
        errors.append("%s is in %s only" % (" ".join(key), a if key in ha else b))
    for key in sorted(set(ha) & set(hb)):
        for x, y in zip(ha[key], hb[key]):
            if (x is None) != (y is None) or (x is not None and abs(x - y) > SAME_PS):
                errors.append("%s: %s in %s, %s in %s" % (" ".join(key), x, a, y, b))
                break
    return errors, len(ha)


def pairs(ledger, reference):
    """(errors, lines): the ledger's arcs against the pairs a direct search
    times a path between."""
    got = {key[1:]: v for key, v in halves(ledger).items() if key[0] == "arc"}
    want = {}
    with open(reference) as f:
        for n, line in enumerate(f, 1):
            where = "%s:%d" % (reference, n)
            fields = line.split()
            if not fields or fields[0] == "#":
                continue
            if fields[0] != "pair" or len(fields) != 5:
                raise LedgerError("%s: not a pair: %s" % (where, line.strip()))
            want[(fields[1], fields[2])] = [
                crossing_ledger.number(v, where) for v in fields[3:5]
            ]
    errors = []
    for these, what in (
        (sorted(set(want) - set(got)), "pairs with a timed path are no arc"),
        (sorted(set(got) - set(want)), "arcs have no timed path"),
    ):
        if these:
            errors.append(
                "%d %s: %s"
                % (len(these), what, crossing_ledger.some(["%s>%s" % p for p in these]))
            )
    off = []
    for p in sorted(set(want) & set(got)):
        # the routed and the zero-wire delay, each against its search
        if any(
            x is None or y is None or abs(x - y) > FUZZ_PS
            for x, y in zip(got[p], want[p])
        ):
            off.append("%s>%s %s against %s ps;" % (p[0], p[1], got[p], want[p]))
    if off:
        errors.append(
            "%d arcs are not their pair's slowest path: %s"
            % (len(off), crossing_ledger.some(off, 5))
        )
    lines = [
        "%d pairs a direct search times a path between, %d arcs in the ledger"
        % (len(want), len(got))
    ]
    return errors, lines


def spot(path):
    """(errors, lines): the pins the ledger checked against a path search."""
    errors = []
    lines = []
    shown = set()
    for fields in comments(path, "spot"):
        try:
            way, pin, n = fields[0], fields[1], int(fields[2])
            least, most, half = [float(fields[i]) for i in (4, 6, 8)]
        except (IndexError, ValueError):
            raise LedgerError("%s: not a spot line: %s" % (path, " ".join(fields)))
        if abs(half - most) > PRINTED_PS:
            errors.append(
                "%s %s: the ledger holds %.2f ps, the slowest of the %d registers "
                "behind it %.2f" % (way, pin, half, n, most)
            )
        elif n >= 2 and least < most:
            shown.add(way)
            lines.append(
                "spot: %s %s, %d registers behind it, %.2f to %.2f ps: the ledger "
                "holds %.2f" % (way, pin, n, least, most, half)
            )
    for way in ("in", "out"):
        if way not in shown:
            errors.append(
                "no %s pin checked has two registers of different delay behind it: "
                "that a half is the slowest of them all is not shown" % way
            )
    return errors, lines


# a `# miss` line's kind: the line its pins are on, and the half of it
MISSES = {"in2reg": ("in", 0), "reg2out": ("out", 0), "in2out": ("out", 2)}


def miss(path):
    """(errors, lines): the pins over the boundary budgets, counted again
    from the ledger's own halves."""
    errors = []
    lines = []
    got = halves(path)
    total = 0
    for fields in comments(path, "miss"):
        if fields[0] not in MISSES:
            errors.append("no boundary budget was given: a miss is not shown")
            continue
        try:
            kind = fields[0]
            over, pins = [int(v) for v in fields[1].split("/")]
            worst, budget = float(fields[4]), float(fields[6])
        except (IndexError, ValueError):
            raise LedgerError("%s: not a miss line: %s" % (path, " ".join(fields)))
        line, at = MISSES[kind]
        mine = [v[at] for k, v in got.items() if k[0] == line and v[at] is not None]
        # a half within its last printed digit of the budget counts either way
        sure = sum(1 for v in mine if v > budget + PRINTED_PS)
        maybe = sum(1 for v in mine if v >= budget - PRINTED_PS)
        if pins != len(mine) or not sure <= over <= maybe:
            errors.append(
                "%s: the ledger counts %d of %d pins over %g ps, its halves put "
                "%d of %d over" % (kind, over, pins, budget, sure, len(mine))
            )
        elif mine and abs(max(mine) - worst) > PRINTED_PS:
            errors.append(
                "%s: the ledger's worst is %.2f ps, its halves' %.2f"
                % (kind, worst, max(mine))
            )
        total += over
        lines.append(
            "miss: %s, %d of %d pins over %g ps, worst %.2f ps"
            % (kind, over, pins, budget, worst)
        )
    if not total and not errors:
        errors.append("no pin is over a boundary budget: a miss is not shown")
    if total:
        lines.append(
            "miss: %d pins over their budgets, and the ledger was written" % total
        )
    return errors, lines


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--same", nargs=2, metavar="LEDGER")
    ap.add_argument("--pairs", nargs=2, metavar=("LEDGER", "PAIRS"))
    ap.add_argument("--top", help="crossing_ledger_top.tcl's paths")
    ap.add_argument("--hub", help="the hub's ledger")
    ap.add_argument("--block", action="append", default=[], metavar="M=LEDGER")
    ap.add_argument("--max-skew", type=float, default=20.0, help="ps")
    ap.add_argument(
        "--zero", metavar="PART", help="hub, or a block: its halves at zero"
    )
    ap.add_argument("--zero-half", action="store_true", help="one half at zero")
    ap.add_argument("--drop", metavar="M", help="a block: its ledger left out")
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--miss", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.same:
            errors, n = same(*args.same)
            lines = ["%d pins and feed-throughs compared" % n]
        elif args.pairs:
            errors, lines = pairs(*args.pairs)
        else:
            if not args.top or not args.hub:
                ap.error("--top and --hub, --same, or --pairs")
            parts = crossing_ledger.parse_blocks(args.block)
            if args.drop not in [None] + list(parts):
                ap.error("--drop %s: not a block" % args.drop)
            parts.pop(args.drop, None)
            parts[crossing_ledger.HUB] = args.hub
            if args.zero and args.zero not in parts:
                ap.error("--zero %s: not a part" % args.zero)
            paths = read_top(args.top)
            control = []
            if args.zero or args.zero_half:
                # a Bazel test's own; never the system's
                scratch = os.environ.get("TEST_TMPDIR")
                if not scratch:
                    ap.error("TEST_TMPDIR names where a ledger is written again")
                out = os.path.join(tempfile.mkdtemp(dir=scratch), "zero.txt")
                if args.zero:
                    parts[args.zero] = zeroed(parts[args.zero], out)
                else:
                    name, pin, net = half_zeroed(paths, parts, out)
                    parts[name] = out
                    control = ["one half at zero: %s's launch into %s" % (name, net)]
            hub = parts.pop(crossing_ledger.HUB)
            # the budget sorts the rows into classes, which are not checked
            rows, _, _ = crossing_ledger.join(hub, parts, 0.0)
            errors, lines = check(rows, paths, args.max_skew)
            lines = control + lines
            for wanted, look in ((args.spot, spot), (args.miss, miss)):
                if wanted:
                    more, said = look(args.hub)
                    errors += more
                    lines += said
    except LedgerError as e:
        sys.exit("crossing_ledger_check: %s" % e)
    print("\n".join(lines))
    if errors:
        sys.exit("\n".join("crossing_ledger_check: %s" % e for e in errors))


if __name__ == "__main__":
    main(sys.argv[1:])
