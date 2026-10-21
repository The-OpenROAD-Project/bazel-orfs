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
EPS = 1.0  # --eps: an endpoint faster or slower by more than this counts


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


def compare(control, other, eps=EPS):
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
        if d < -eps:
            faster += 1
            gain -= d
        elif d > eps:
            slower += 1
            loss += d
    return faster, slower, gain, loss, unmatched


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clock", type=float, required=True)
    ap.add_argument("--eps", type=float, default=EPS)
    ap.add_argument("--unit", default="ps")
    ap.add_argument("runs", nargs="+", metavar="name=endpoints.tsv")
    args = ap.parse_args(argv)
    runs = []
    for r in args.runs:
        name, _, path = r.partition("=")
        runs.append((name, read(path)))
    cname, control = runs[0]
    cmin = max(control.values())
    u = args.unit
    # ps to a tenth, ns to a picosecond
    p = "%.1f" if u == "ps" else "%.3f"
    print(
        "| keep list | min reg2reg period | vs %s | band: faster | band: slower "
        "| %s faster | %s slower |" % (cname, u, u)
    )
    print("|---|---:|---:|---:|---:|---:|---:|")
    for name, ends in runs:
        pmin = max(ends.values())
        if name == cname:
            print(
                ("| %s | " + p + " %s (%.1f %% of %g) | – | – | – | – | – |")
                % (name, pmin, u, 100 * pmin / args.clock, args.clock)
            )
            continue
        f, s, g, l, n = compare(control, ends, args.eps)
        print(
            ("| %s | " + p + " %s | %+.1f %% | %d | %d | " + p + " | " + p + " |%s")
            % (
                name,
                pmin,
                u,
                100 * (pmin - cmin) / cmin,
                f,
                s,
                g,
                l,
                " (%d endpoints unmatched)" % n if n else "",
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
