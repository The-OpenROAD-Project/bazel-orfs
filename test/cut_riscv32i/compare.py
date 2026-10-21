"""Keep lists compared at global route, as ORFS #4583 proposes.

    compare.py --clock PS <name>=<endpoints.tsv> ... > table.md

The first file is the control. For each: the minimum reg2reg period (the
clock period minus the reg2reg worst slack) in ps and in percent of the
control's, and, against the control, the endpoints in the band: those
within 10 % of the control's minimum period in either run, how many got
faster and slower by more than 1 ps, and by how much in all. Endpoints
are matched by name; one present in only one run is counted apart.
"""

import argparse
import sys

BAND = 0.10
EPS = 1.0


def read(path):
    ends = {}
    with open(path) as f:
        for line in f:
            name, period = line.rstrip("\n").split("\t")
            # a kept module's registers are riscv/dp/rf/..., a flattened
            # one's riscv.dp.rf...: the same register either way
            ends[name.replace("/", ".")] = float(period)
    if not ends:
        raise ValueError("%s has no reg2reg endpoint" % path)
    return ends


def compare(control, other):
    """(faster, slower, ps faster summed, ps slower summed, unmatched)
    of the band's endpoints, other against control."""
    floor = max(control.values()) * (1 - BAND)
    faster = slower = 0
    gain = loss = 0.0
    unmatched = 0
    for name in set(control) | set(other):
        a = control.get(name)
        b = other.get(name)
        if a is None or b is None:
            unmatched += 1
            continue
        if max(a, b) < floor:
            continue
        d = b - a
        if d < -EPS:
            faster += 1
            gain -= d
        elif d > EPS:
            slower += 1
            loss += d
    return faster, slower, gain, loss, unmatched


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clock", type=float, required=True)
    ap.add_argument("runs", nargs="+", metavar="name=endpoints.tsv")
    args = ap.parse_args(argv)
    runs = []
    for r in args.runs:
        name, _, path = r.partition("=")
        runs.append((name, read(path)))
    cname, control = runs[0]
    cmin = max(control.values())
    print(
        "| keep list | min reg2reg period | vs %s | band: faster | band: slower "
        "| ps faster | ps slower |" % cname
    )
    print("|---|---:|---:|---:|---:|---:|---:|")
    for name, ends in runs:
        pmin = max(ends.values())
        if name == cname:
            print(
                "| %s | %.1f ps (%.1f %% of %g) | – | – | – | – | – |"
                % (name, pmin, 100 * pmin / args.clock, args.clock)
            )
            continue
        f, s, g, l, u = compare(control, ends)
        print(
            "| %s | %.1f ps | %+.1f %% | %d | %d | %.0f | %.0f |%s"
            % (
                name,
                pmin,
                100 * (pmin - cmin) / cmin,
                f,
                s,
                g,
                l,
                " (%d endpoints unmatched)" % u if u else "",
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
