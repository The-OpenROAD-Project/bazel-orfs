"""The crossing ledger checked against the top level it stands in for.

    crossing_ledger_check.py --top <top.txt> --hub <ledger> --block <M>=<ledger>...
        [--max-skew <ps>] [--zero <part>] [--drop <M>] [--spot] [--miss]
    crossing_ledger_check.py --same <ledger> <ledger>

<top.txt> is crossing_ledger_top.tcl's: the register-to-register paths
the routed top level times through each crossing net, each with its
clock taken out (free). The ledger (crossing_ledger.py) holds for a net
the most any path through it needs, summed from halves read in parts
that never saw each other, so:

  - no path through a net needs more than the ledger holds for the net;
  - the net's slowest path needs as much as the ledger holds;
  - the ledger has a row for the nets the top level times a path
    through, and for no other;
  - no path's clock adds more than --max-skew to it: the ledger holds no
    clock, and says nothing of a top level whose clock tree is broken.

The first two within the tolerance, the larger of 20 ps and 10 % of the
path: a part does not see the slew that arrives at its inputs or the
load its outputs drive.

--zero <part> (hub, or a block) and --drop <M> are the negative
controls: the check with that part's halves all zero, or without that
block's ledger. Both must fail.

--spot: the hub's ledger checked a pin of each direction with two or
more registers of different delay behind it against a path search, and
holds the slowest (`# spot` lines). --miss: its `# miss` lines count the
pins its own halves put over the boundary budgets, some pin is over, and
the ledger was written all the same.

--same: two ledgers of one part, read under different boundary
constraints, hold the same halves.
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
    need = {r["net"]: r["need"] for r in rows}
    timed = {net: got for net, got in paths.items() if got}
    errors = []
    lost = sorted(set(need) - set(timed))
    if lost:
        errors.append(
            "the top level times no path through %d nets the ledger has a row for: %s"
            % (len(lost), crossing_ledger.some(lost))
        )
    blind = sorted(set(timed) - set(need))
    if blind:
        errors.append(
            "the ledger has no row for %d nets the top level times a path through: %s"
            % (len(blind), crossing_ledger.some(blind))
        )
    under = []
    over = []
    apart = []
    clock = []
    for net in sorted(set(timed) & set(need)):
        for p in timed[net]:
            clock.append((p["clock"], net, p))
            short = p["free"] - need[net]
            if short > tolerance(p["free"]):
                under.append((short, net, p))
        worst = max(p["free"] for p in timed[net])
        apart.append((need[net] - worst, net, worst))
        if need[net] - worst > tolerance(worst):
            over.append((need[net] - worst, net, worst))
    if under:
        under.sort(key=lambda u: (-u[0], u[1]))
        errors.append(
            "ledger under the top level: %d paths through %d nets need more than "
            "the net's halves sum to, by more than the tolerance: %s"
            % (
                len(under),
                len(set(net for _, net, _ in under)),
                crossing_ledger.some(
                    [
                        "%s %.1f against %.1f ps (%s);"
                        % (net, need[net], p["free"], p["ends"])
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
            "slowest path through the net needs, by more than the tolerance: %s"
            % (
                len(over),
                crossing_ledger.some(
                    [
                        "%s %.1f against %.1f ps;" % (net, need[net], worst)
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
            % (far[0], far[1], need[far[1]], far[2]),
            "worst of its path %.2f %%: %s, %.1f against %.1f ps"
            % (100 * rel[0] / rel[2], rel[1], need[rel[1]], rel[2]),
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
        skewed = max(clock, key=lambda c: abs(c[0]))
        if abs(skewed[0]) > max_skew:
            errors.append(
                "the top level's clock adds %.1f ps to a path through %s (%s), over "
                "the %g ps the ledger is checked within"
                % (skewed[0], skewed[1], skewed[2]["ends"], max_skew)
            )
    return errors, lines


def halves(path):
    """A ledger's numbers by line, {(kind, pin...): [ps or None]}: an
    out's launch and slowest feed-through, an in's capture, an arc's
    delay, each as routed and at zero wire."""
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
            elif fields[0] == "arc" and len(fields) == 6:
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
    spans = {"out": (2, 6), "in": (2, 4), "arc": (3, 5)}
    with open(path) as f, open(out, "w") as g:
        for line in f:
            fields = line.split()
            if fields and fields[0] in spans:
                a, b = spans[fields[0]]
                fields[a:b] = ["-" if v == "-" else "0.00" for v in fields[a:b]]
                line = " ".join(fields) + "\n"
            g.write(line)
    return out


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
    ap.add_argument("--top", help="crossing_ledger_top.tcl's paths")
    ap.add_argument("--hub", help="the hub's ledger")
    ap.add_argument("--block", action="append", default=[], metavar="M=LEDGER")
    ap.add_argument("--max-skew", type=float, default=20.0, help="ps")
    ap.add_argument(
        "--zero", metavar="PART", help="hub, or a block: its halves at zero"
    )
    ap.add_argument("--drop", metavar="M", help="a block: its ledger left out")
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--miss", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.same:
            errors, n = same(*args.same)
            lines = ["%d pins and feed-throughs compared" % n]
        else:
            if not args.top or not args.hub:
                ap.error("--top and --hub, or --same")
            parts = crossing_ledger.parse_blocks(args.block)
            if args.drop not in [None] + list(parts):
                ap.error("--drop %s: not a block" % args.drop)
            parts.pop(args.drop, None)
            parts[crossing_ledger.HUB] = args.hub
            if args.zero:
                if args.zero not in parts:
                    ap.error("--zero %s: not a part" % args.zero)
                d = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
                parts[args.zero] = zeroed(parts[args.zero], os.path.join(d, "zero.txt"))
            hub = parts.pop(crossing_ledger.HUB)
            # the budget sorts the rows into classes, which are not checked
            rows, _, _ = crossing_ledger.join(hub, parts, 0.0)
            errors, lines = check(rows, read_top(args.top), args.max_skew)
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
