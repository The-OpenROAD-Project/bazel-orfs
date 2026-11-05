"""The flattened top level's check, on a design small enough to time
whole: the top level that takes its macros' boundary logic over
(top_level.tcl, TOP_FLATTEN) passes a crossing the top level as built
fails, and leaves every macro's own paths where they were.

    top_flat_check.py <period_ps> <whole.txt> <whole_flat.txt>

Each report is crossing_paths.tcl's: need_ps kind from to start end ...,
the paths over its budget. At period_ps the worst crossing of whole.txt
fails and that of whole_flat.txt passes; each macro's worst path inside
it needs no more than it did, or the report's budget when it had none
listed, within TOL_PS.
"""

import sys

TOL_PS = 1.0


def read(path):
    """The report's budget, and the worst need per (kind, from, to)."""
    budget = 0.0
    worst = {}
    with open(path) as f:
        for line in f:
            fields = line.split()
            if line.startswith("#"):
                if "over" in fields:
                    budget = float(fields[fields.index("over") + 1])
                continue
            if len(fields) < 4:
                continue
            key = (fields[1], fields[2], fields[3])
            worst[key] = max(worst.get(key, 0.0), float(fields[0]))
    return budget, worst


def crossing(worst):
    return max((v for k, v in worst.items() if k[0] == "crossing"), default=0.0)


def check(period, whole, flat):
    """The broken rules, as messages."""
    budget, before = whole
    _, after = flat
    errors = []
    if crossing(before) <= period:
        errors.append(
            "the top level as built passes %.1f ps (worst crossing %.1f):"
            " nothing for the flattened one to fix" % (period, crossing(before))
        )
    if crossing(after) > period:
        errors.append(
            "the flattened top level fails %.1f ps (worst crossing %.1f, %.1f"
            " as built)" % (period, crossing(after), crossing(before))
        )
    for key in sorted(set(before) | set(after)):
        if key[0] != "inside":
            continue
        was = before.get(key, budget)
        now = after.get(key, 0.0)
        if now > was + TOL_PS:
            errors.append(
                "%s's own paths need %.1f ps, %.1f as built" % (key[1], now, was)
            )
    return errors


def main(argv):
    period = float(argv[1])
    errors = check(period, read(argv[2]), read(argv[3]))
    for e in errors:
        print("top_flat_check: " + e, file=sys.stderr)
    if errors:
        return 1
    print("top_flat_check: worst crossing passes %.1f ps flattened" % period)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
