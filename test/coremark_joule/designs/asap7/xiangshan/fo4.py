"""The fanout-of-4 inverter delay of a Liberty library, from its tables.

A chain of INVx1, each driving four copies of itself: the steady state of
that chain, where the input slew of a stage is the output slew of the one
before, is the FO4 delay. Rising and falling stages alternate, so the FO4
delay is the mean of the two. No wire load: the published ASAP7 figures
include the cell's extracted layout parasitics and so do the tables.
"""

import gzip
import re
import sys


def _block(text, header):
    """The body of the brace block that follows `header`."""
    start = text.index(header)
    i = text.index("{", start) + 1
    depth = 1
    j = i
    while depth:
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        j += 1
    return text[i : j - 1]


def _floats(s):
    return [float(x) for x in re.findall(r"[-+0-9.eE]+", s)]


def _table(timing, name):
    body = _block(timing, name + " (")
    index_1 = _floats(re.search(r"index_1\s*\(([^)]*)\)", body).group(1))
    index_2 = _floats(re.search(r"index_2\s*\(([^)]*)\)", body).group(1))
    values = _floats(re.search(r"values\s*\((.*?)\)\s*;", body, re.S).group(1))
    rows = [values[k * len(index_2) : (k + 1) * len(index_2)] for k in range(len(index_1))]
    return index_1, index_2, rows


def _bracket(axis, x):
    """The two indices around x, extrapolating from the end segments."""
    k = 0
    while k < len(axis) - 2 and x > axis[k + 1]:
        k += 1
    return k, (x - axis[k]) / (axis[k + 1] - axis[k])


def lookup(table, slew, load):
    """Bilinear interpolation, as an STA tool does on an NLDM table."""
    index_1, index_2, rows = table
    i, u = _bracket(index_1, slew)
    j, v = _bracket(index_2, load)
    a = rows[i][j] + v * (rows[i][j + 1] - rows[i][j])
    b = rows[i + 1][j] + v * (rows[i + 1][j + 1] - rows[i + 1][j])
    return a + u * (b - a)


def read_lib(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        return f.read()


def fo4(lib_text, cell):
    """FO4 delay in the library's time unit (ps for ASAP7)."""
    body = _block(lib_text, "cell (%s)" % cell)
    cin = float(re.search(r"\bcapacitance\s*:\s*([0-9.eE+-]+)", _block(body, "pin (A)")).group(1))
    timing = _block(_block(body, "pin (Y)"), "timing ()")
    cell_rise = _table(timing, "cell_rise")
    cell_fall = _table(timing, "cell_fall")
    rise_transition = _table(timing, "rise_transition")
    fall_transition = _table(timing, "fall_transition")
    load = 4 * cin
    rise_slew = fall_slew = 10.0
    for _ in range(200):
        # A rising input makes a falling output, whose slew drives the next.
        d_fall = lookup(cell_fall, rise_slew, load)
        fall_slew_next = lookup(fall_transition, rise_slew, load)
        d_rise = lookup(cell_rise, fall_slew_next, load)
        rise_slew_next = lookup(rise_transition, fall_slew_next, load)
        converged = abs(rise_slew_next - rise_slew) < 1e-9 and abs(fall_slew_next - fall_slew) < 1e-9
        rise_slew, fall_slew = rise_slew_next, fall_slew_next
        if converged:
            break
    return (d_rise + d_fall) / 2


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: fo4.py <lib[.gz]> <inverter cell>")
    print("%.3f" % fo4(read_lib(argv[1]), argv[2]))


if __name__ == "__main__":
    main(sys.argv)
