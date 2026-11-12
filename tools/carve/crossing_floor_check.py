"""How much of each crossing is wire, from crossing_floor.tcl's reports:
per group of ends (start macro, macros between, end macro), the ends over
the budget as placed and those still over with no signal wire, and the
worst of each. It fails when the second reading's worst crossing is not
lower than the first's, and when an end's capture clock delay differs
between the readings: the clock's wires are as placed in both. An end is
over the budget when it needs more than it, as crossing_report.py counts.
crossing_floor.tcl writes both readings' capture clock delay for every end
the first reading has, with or without a crossing path into it in the
second; the clock check compares them there, and fails on such an end
without them, and when it compared no row.

    crossing_floor_check.py <budget ps> <floor dir> [--control <control dir>]
                            [--sets <sets.txt>]

Each dir holds cross.txt.<n>, one per set, in the format crossing_floor.tcl
writes and describes; with --sets (crossing_plan.tcl's), one for every set
and none else. An end is its pin's name and its cell's place, and is in a
group by its worst row over the sets, spelt as crossing_ends.py spells it:
from>through...>to. With --control, the control (FLOOR_CONTROL=1, the
second reading as placed too) must give the same readings twice in every
row, and the check must fail on it, for its reason: with nothing taken
away, the worst crossing is not lower.
"""

import os
import re
import sys

EPS = 0.05
HEADER = "# crossing_floor "
COLUMNS = (
    "placed_ps",
    "floor_ps",
    "clock_placed_ps",
    "clock_floor_ps",
    "from_macro",
    "to_macro",
    "through_macros",
    "startpoint",
    "endpoint",
    "end_x end_y",
)


def number(field):
    return None if field == "-" else float(field)


def read_report(path):
    """(header {key: value}, rows): each row a dict of COLUMNS, the
    readings as floats or None."""
    header = None
    rows = []
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if line.startswith(HEADER):
                header = dict(kv.split("=", 1) for kv in line[len(HEADER) :].split())
                continue
            if line.startswith("#") or not line:
                continue
            fields = line.split("\t")
            if len(fields) != len(COLUMNS):
                raise ValueError(
                    "%s:%d: %d fields, not %d" % (path, n, len(fields), len(COLUMNS))
                )
            row = dict(zip(COLUMNS, fields))
            for c in COLUMNS[:4]:
                row[c + "_text"] = row[c]
                row[c] = number(row[c])
            rows.append(row)
    if header is None:
        raise ValueError("%s: no '%s' line" % (path, HEADER.strip()))
    return header, rows


def read_dir(d):
    """{set number: (header, rows)} for every cross.txt.<n> in d."""
    sets = sorted(
        int(m.group(1))
        for m in (re.fullmatch(r"cross\.txt\.(\d+)", f) for f in os.listdir(d))
        if m
    )
    return {n: read_report(os.path.join(d, "cross.txt.%d" % n)) for n in sets}


def count_sets(path):
    """crossing_plan.tcl's sets: how many lines are neither blank nor a
    comment, as crossing_time_sets.tcl numbers them."""
    with open(path) as f:
        return sum(1 for line in f if line.strip() and not line.startswith("#"))


def sets_errors(d, reports, n_sets):
    """Every set has its report in d, and no report is of a set that is
    not there."""
    errors = [
        "set %d has no report (cross.txt.%d) in %s" % (n, n, d)
        for n in range(n_sets)
        if n not in reports
    ]
    errors += [
        "cross.txt.%d in %s is the report of none of the %d sets" % (n, d, n_sets)
        for n in sorted(reports)
        if n >= n_sets
    ]
    return errors


def group_of(row):
    """from>through...>to, as crossing_ends.py spells a group."""
    via = [m for m in row["through_macros"].split(",") if m not in ("", "-")]
    return ">".join([row["from_macro"]] + via + [row["to_macro"]])


def worst(values):
    values = [v for v in values if v is not None]
    return max(values) if values else None


def ends(reports):
    """{(endpoint, place): (group, placed, floor)}: an end's worst reading
    of each kind over the sets, its group its worst placed row's (its
    worst second reading's when no set has it as placed)."""
    rows = {}
    for _, (_, rs) in sorted(reports.items()):
        for r in rs:
            rows.setdefault((r["endpoint"], r["end_x end_y"]), []).append(r)
    out = {}
    for key, rs in rows.items():
        first = max(
            rs,
            key=lambda r: (
                r["placed_ps"] is not None,
                r["placed_ps"] if r["placed_ps"] is not None else r["floor_ps"],
            ),
        )
        out[key] = (
            group_of(first),
            worst(r["placed_ps"] for r in rs),
            worst(r["floor_ps"] for r in rs),
        )
    return out


def fmt(v):
    return "-" if v is None else "%.1f" % v


def check(budget, reports, mode="floor"):
    """(lines, errors) for one directory's reports."""
    lines = []
    errors = []
    if not reports:
        return lines, ["no crossing_floor reports (cross.txt.<n>)"]
    for n, (header, _) in sorted(reports.items()):
        if header.get("mode") != mode:
            errors.append(
                "set %d: mode %s, not %s: the wrong directory"
                % (n, header.get("mode"), mode)
            )
    data_min = min(float(h.get("data_min_ps", budget)) for h, _ in reports.values())
    by_end = ends(reports)
    if not by_end:
        errors.append(
            "no crossing end over %.0f ps as placed: nothing to measure" % data_min
        )
        return lines, errors
    # the clock's wires are as placed in both readings, compared on every
    # row that has both readings' capture clock delay: every end of the
    # first reading, with or without a path into it in the second
    compared = 0
    no_path = 0
    differ = 0
    for n, (_, rows) in sorted(reports.items()):
        both = []
        missing = []
        for r in rows:
            if r["clock_placed_ps"] is not None and r["clock_floor_ps"] is not None:
                both.append(r)
            elif r["placed_ps"] is not None:
                missing.append(r)
        changed = [
            r for r in both if abs(r["clock_placed_ps"] - r["clock_floor_ps"]) > EPS
        ]
        compared += len(both)
        no_path += sum(1 for r in both if r["floor_ps"] is None)
        differ += len(changed)
        if missing:
            r = missing[0]
            errors.append(
                "set %d: %d ends of the first reading without both readings'"
                " capture clock delay, %s: %s ps as placed, %s ps in the"
                " second: its clock is not compared"
                % (
                    n,
                    len(missing),
                    r["endpoint"],
                    r["clock_placed_ps_text"],
                    r["clock_floor_ps_text"],
                )
            )
        if changed:
            r = changed[0]
            errors.append(
                "set %d: the capture clock delay differs between the readings"
                " at %d ends, %s: %s ps as placed, %s ps in the second: the"
                " clock is not as placed in the second reading"
                % (
                    n,
                    len(changed),
                    r["endpoint"],
                    r["clock_placed_ps_text"],
                    r["clock_floor_ps_text"],
                )
            )
    groups = {}
    for group, placed, floor in by_end.values():
        g = groups.setdefault(group, [0, None, 0, None])
        if placed is not None and placed > budget:
            g[0] += 1
            g[1] = worst([g[1], placed])
        if floor is not None and floor > budget:
            g[2] += 1
            g[3] = worst([g[3], floor])
    worst_placed = worst(p for _, p, _ in by_end.values())
    worst_floor = worst(f for _, _, f in by_end.values())
    over_placed = sum(g[0] for g in groups.values())
    over_floor = sum(g[2] for g in groups.values())
    lines.append(
        "crossing floor: %d ends over %.0f ps as placed, worst %s ps; %d still"
        " over with no signal wire, worst %s; sets %d; ends under %.0f ps"
        " not reported"
        % (
            over_placed,
            budget,
            fmt(worst_placed),
            over_floor,
            (
                "%s ps" % fmt(worst_floor)
                if worst_floor is not None
                else "under %.0f ps" % data_min
            ),
            len(reports),
            data_min,
        )
    )
    lines.append(
        "clock: %d rows compared, %d of them with no crossing path over %.0f ps"
        " in the second reading; the capture clock delay differs in %d"
        % (compared, no_path, data_min, differ)
    )
    if not compared:
        errors.append(
            "the clock check compared no row: no end has both readings'"
            " capture clock delay, so nothing shows the clock as placed in"
            " the second"
        )
    lines.append("group\tover_placed\tworst_placed_ps\tover_no_wire\tworst_no_wire_ps")
    for group, g in sorted(groups.items(), key=lambda kv: (-kv[1][0], kv[0])):
        if g[0] or g[2]:
            lines.append("\t".join([group, str(g[0]), fmt(g[1]), str(g[2]), fmt(g[3])]))
    # no reading in the second: under data_min, below every first reading
    if worst_placed is None:
        errors.append("no end has a reading as placed")
    elif worst_floor is not None and worst_floor >= worst_placed:
        errors.append(
            "the worst crossing with no signal wire, %s ps, is not lower than"
            " as placed, %s ps" % (fmt(worst_floor), fmt(worst_placed))
        )
    return lines, errors


def identical(reports):
    """The control's two readings, the same in every row; errors."""
    errors = []
    rows = 0
    for n, (_, rs) in sorted(reports.items()):
        for r in rs:
            rows += 1
            if (r["placed_ps_text"], r["clock_placed_ps_text"]) != (
                r["floor_ps_text"],
                r["clock_floor_ps_text"],
            ):
                errors.append(
                    "control: set %d, %s: %s ps as placed, %s ps the second"
                    " time (clock %s, %s): the readings differ with the"
                    " wires as placed"
                    % (
                        n,
                        r["endpoint"],
                        r["placed_ps_text"],
                        r["floor_ps_text"],
                        r["clock_placed_ps_text"],
                        r["clock_floor_ps_text"],
                    )
                )
    return rows, errors


def option(args, name):
    """The value of --name, taken out of args; None when not given."""
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        return None
    value = args[i + 1]
    del args[i : i + 2]
    return value


def main(argv):
    args = list(argv)
    control_dir = option(args, "--control")
    sets_path = option(args, "--sets")
    if len(args) != 2 or any(a.startswith("--") for a in args):
        print(__doc__)
        return 2
    budget = float(args[0])
    floor = read_dir(args[1])
    lines, errors = check(budget, floor)
    n_sets = None if sets_path is None else count_sets(sets_path)
    if n_sets is not None:
        errors += sets_errors(args[1], floor, n_sets)
    if control_dir is not None:
        control = read_dir(control_dir)
        if n_sets is not None:
            errors += sets_errors(control_dir, control, n_sets)
        rows, differ = identical(control)
        errors += differ
        _, control_errors = check(budget, control, mode="control")
        not_lower = [e for e in control_errors if "is not lower" in e]
        if not rows:
            errors.append("control: no rows in %s" % control_dir)
        elif not differ:
            lines.append(
                "control: %d rows, the two readings identical in every one" % rows
            )
        if not not_lower:
            errors.append(
                "control: the check does not fail on the control, so it"
                " cannot tell a floor from no change: %s" % control_errors
            )
        else:
            lines.append(
                "control: the check fails on it, as it must: %s" % not_lower[0]
            )
        errors += [e for e in control_errors if "is not lower" not in e]
    for line in lines:
        print(line)
    for e in errors:
        print("FAIL: %s" % e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
