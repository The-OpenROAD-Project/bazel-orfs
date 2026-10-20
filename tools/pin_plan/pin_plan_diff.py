"""Two pin plans of one part side by side (pin_plan.tcl's outputs), to tell
whether a plan made from the placement says the same as one made from
global route.

usage: pin_plan_diff.py OUT A_NAME B_NAME A_REPORT B_REPORT A_MACROS B_MACROS
           [A_PINS B_PINS ...]

For every macro pin script pair: the pins whose side differs, and per side
how far the stretch's ends moved. For the macro places: how far each macro
moved and whether its orientation changed. From the reports: the pins
facing away from their logic as each plan's stage saw them."""

import re
import sys

REGION = re.compile(
    r"^set_io_pin_constraint -region (\w+):(-?[\d.]+)-(-?[\d.]+) -pin_names \{(.*)\}$"
)
PLACE = re.compile(
    r"^place_macro -macro_name \{(.*)\} -location \{(\S+) (\S+)\} -orientation (\S+) -exact$"
)
TOTAL = re.compile(r"^total (\d+) pins, (\d+) facing away from their logic$", re.M)


def read_pins(path):
    """{side: (lo, hi, [pin, ...])} of a pin script."""
    sides = {}
    with open(path) as f:
        for line in f:
            m = REGION.match(line.strip())
            if m:
                side, lo, hi, names = m.groups()
                # Tcl braces a name with brackets in it: {r0_data[3]}
                sides[side] = (
                    float(lo),
                    float(hi),
                    [n.strip("{}") for n in names.split()],
                )
    return sides


def read_places(path):
    """{instance: (x, y, orientation)} of a macro placement script."""
    places = {}
    with open(path) as f:
        for line in f:
            m = PLACE.match(line.strip())
            if m:
                name, x, y, orient = m.groups()
                places[name] = (float(x), float(y), orient)
    return places


def read_total(path):
    with open(path) as f:
        text = f.read()
    m = TOTAL.search(text)
    if not m:
        raise ValueError("%s: no total line" % path)
    return int(m.group(1)), int(m.group(2))


def side_of(sides):
    return {p: side for side, (_, _, pins) in sides.items() for p in pins}


def diff_pins(a, b):
    """Lines comparing two pin scripts, and the number of pins whose side
    differs, of how many."""
    sa, sb = side_of(a), side_of(b)
    if set(sa) != set(sb):
        raise ValueError(
            "the plans name different pins: %d only in A, %d only in B"
            % (len(set(sa) - set(sb)), len(set(sb) - set(sa)))
        )
    moved = sorted(p for p in sa if sa[p] != sb[p])
    lines = []
    for side in ["left", "right", "bottom", "top"]:
        if side not in a and side not in b:
            continue
        na = len(a[side][2]) if side in a else 0
        nb = len(b[side][2]) if side in b else 0
        if side in a and side in b:
            shift = max(abs(a[side][0] - b[side][0]), abs(a[side][1] - b[side][1]))
            lines.append(
                "  %-6s A %4d pins %9.3f-%9.3f  B %4d pins %9.3f-%9.3f  ends moved %.3f um"
                % (side, na, a[side][0], a[side][1], nb, b[side][0], b[side][1], shift)
            )
        else:
            only = a if side in a else b
            lines.append(
                "  %-6s only in %s, %d pins %9.3f-%9.3f"
                % (
                    side,
                    "A" if side in a else "B",
                    max(na, nb),
                    only[side][0],
                    only[side][1],
                )
            )
    for p in moved[:20]:
        lines.append("  %s: %s -> %s" % (p, sa[p], sb[p]))
    if len(moved) > 20:
        lines.append("  ... and %d more" % (len(moved) - 20))
    return lines, len(moved), len(sa)


def diff_places(a, b):
    """Lines comparing two macro placements, and the largest move in um."""
    if set(a) != set(b):
        raise ValueError("the placements name different macros")
    lines = []
    worst = 0.0
    for name in sorted(a):
        (xa, ya, oa), (xb, yb, ob) = a[name], b[name]
        d = abs(xa - xb) + abs(ya - yb)
        worst = max(worst, d)
        if d > 0 or oa != ob:
            lines.append(
                "  %s: (%.3f, %.3f) %s -> (%.3f, %.3f) %s, %.3f um"
                % (name, xa, ya, oa, xb, yb, ob, d)
            )
    return lines, worst


def main(argv):
    out, a_name, b_name, a_report, b_report, a_macros, b_macros = argv[:7]
    pairs = argv[7:]
    if len(pairs) % 2:
        raise ValueError("pin scripts come in pairs")
    lines = ["# pin_plan_diff.py: A = %s, B = %s" % (a_name, b_name)]
    for label, path in [(a_name, a_report), (b_name, b_report)]:
        pins, away = read_total(path)
        lines.append(
            "%s: %d pins, %d facing away from their logic" % (label, pins, away)
        )
    moved_total = 0
    pins_total = 0
    for pa, pb in zip(pairs[0::2], pairs[1::2]):
        body, moved, n = diff_pins(read_pins(pa), read_pins(pb))
        lines.append(
            "%s: %d of %d pins on another side" % (pa.split("/")[-1], moved, n)
        )
        lines += body
        moved_total += moved
        pins_total += n
    body, worst = diff_places(read_places(a_macros), read_places(b_macros))
    lines.append("macro places: largest move %.3f um (Manhattan)" % worst)
    lines += body
    lines.append(
        "summary: %d of %d planned pins on another side, macros moved at most %.3f um"
        % (moved_total, pins_total, worst)
    )
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
