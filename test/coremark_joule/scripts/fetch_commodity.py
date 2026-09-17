#!/usr/bin/env python3
"""Regenerate results/commodity_coremark.csv from the OpenBenchmarking exports.

A.1's commodity rows are extracted from four public result exports. This
takes the extraction out of anyone's hands: for every row in SELECTION it
reads the measured numbers from the export, and --check fails when the
committed CSV and the exports disagree.

It is not a scraper that decides what belongs in the table. The four exports
carry sixty-one system entries between them and this file selects
twenty-seven; the parts left out -- the 2P server variants, the X3D and APU
desktop parts, the Core i5s -- are a choice rather than a rule. SELECTION is
that choice, in one place where it can be reviewed.

So the file splits in two.

  Derived from the export, and verified on every run: iterations_per_s,
  power_w for the rows PTS measured, and the core and thread counts out of
  the Processor line.

  Carried in SELECTION, because the export does not have it: the display
  name, the class, the microarchitecture, the reported clock, and -- for
  the four rows with no PTS power monitor -- the power and where it came
  from. Three of those are a vendor rating and two figures quoted from
  published reviews; the fourth has no figure at all, which is why A.1
  lists the other twenty-six and leaves it out. The power_kind column says
  which is which.

Two columns are carried for reasons worth knowing.

  reported_ghz is inconsistently sourced. Most rows match the clock the
  export's Processor line reports; the 9700X rows and the two Apple rows
  use the vendor's figure, and the 7950X's 5.57 matches neither it nor the
  export's 5.88. Nothing in the study computes with the column -- A.1 does
  not show CoreMark/MHz for a whole package -- so a disagreement is
  reported rather than silently resolved.

  power_min_w and power_max_w are not in the CSV export. PTS flattens a
  monitor to its average there; the spread is on the result page and in the
  JSON export. Nothing reads the two columns, and rows added without a JSON
  export leave them empty.

Usage:
    fetch_commodity.py --exports DIR [--check FILE | --out FILE]

DIR holds the four `<result-id>-result.csv` files. They are Phoronix's data
and are not committed; the result ids below are the citation. Fetch them
from openbenchmarking.org/result/<id> with the page's CSV export, or with
`phoronix-test-suite result-file-to-csv <id>`.
"""

import argparse
import csv
import io
import os
import re
import sys
from collections import namedtuple

# The four exports A.1 is built from. Each is cited by id in the paper's
# reference list; none of them is redistributed here.
SOURCES = {
    "2301109-PTS-SPRREVIE33": "Sapphire Rapids server review, January 2023",
    "2410235-NE-285KARROW68": "Arrow Lake desktop review, October 2024",
    "2407128-PTS-GRAVITON53": "Graviton4 metal comparison, July 2024",
    "2208073-NE-M2REVIEW767": "Apple M2 on Asahi Linux, August 2022",
}

# key      -- the system's name inside the export, which is not the display name
# power    -- None when PTS measured it; otherwise the figure and its source
# spread   -- (min, max) from the result page; absent from the CSV export
Row = namedtuple(
    "Row",
    "result_id key cpu klass uarch cores threads ghz power_kind power spread",
)

# The selection. Ordered as the table prints it.
SELECTION = [
    Row('2301109-PTS-SPRREVIE33', 'EPYC 9654', 'AMD EPYC 9654', 'server', 'Zen 4', '96', '192', '3.71', 'measured', None, ('25.85', '350.86')),
    Row('2301109-PTS-SPRREVIE33', 'EPYC 9554', 'AMD EPYC 9554', 'server', 'Zen 4', '64', '128', '3.76', 'measured', None, ('21.80', '330.39')),
    Row('2301109-PTS-SPRREVIE33', 'EPYC 9374F', 'AMD EPYC 9374F', 'server', 'Zen 4', '32', '64', '4.31', 'measured', None, ('23.18', '252.16')),
    Row('2301109-PTS-SPRREVIE33', 'EPYC 7763', 'AMD EPYC 7763', 'server', 'Zen 3', '64', '128', '2.45', 'measured', None, ('35.78', '232.22')),
    Row('2301109-PTS-SPRREVIE33', 'EPYC 7713', 'AMD EPYC 7713', 'server', 'Zen 3', '64', '128', '2.00', 'measured', None, ('37.96', '230.40')),
    Row('2301109-PTS-SPRREVIE33', 'Xeon Platinum 8490H', 'Intel Xeon Platinum 8490H', 'server', 'Golden Cove (Sapphire Rapids)', '60', '120', '3.50', 'measured', None, ('81.89', '349.74')),
    Row('2301109-PTS-SPRREVIE33', 'Xeon Platinum 8380', 'Intel Xeon Platinum 8380', 'server', 'Sunny Cove (Ice Lake)', '40', '80', '3.40', 'measured', None, ('59.83', '290.90')),
    Row('2410235-NE-285KARROW68', 'Ryzen 9 7950X', 'AMD Ryzen 9 7950X', 'desktop', 'Zen 4', '16', '32', '5.57', 'measured', None, ('17.41', '220.92')),
    Row('2410235-NE-285KARROW68', 'Ryzen 9 7900X', 'AMD Ryzen 9 7900X', 'desktop', 'Zen 4', '12', '24', '5.73', 'measured', None, ('16.73', '180.72')),
    Row('2410235-NE-285KARROW68', 'Ryzen 9 7900', 'AMD Ryzen 9 7900 (65 W)', 'desktop', 'Zen 4', '12', '24', '5.48', 'measured', None, ('20.41', '90.70')),
    Row('2410235-NE-285KARROW68', 'Ryzen 7 7700X', 'AMD Ryzen 7 7700X', 'desktop', 'Zen 4', '8', '16', '5.57', 'measured', None, ('17.60', '130.16')),
    Row('2410235-NE-285KARROW68', 'Ryzen 7 7700', 'AMD Ryzen 7 7700 (65 W)', 'desktop', 'Zen 4', '8', '16', '5.39', 'measured', None, ('14.05', '90.52')),
    Row('2410235-NE-285KARROW68', 'Ryzen 5 7600', 'AMD Ryzen 5 7600 (65 W)', 'desktop', 'Zen 4', '6', '12', '5.17', 'measured', None, None),
    Row('2410235-NE-285KARROW68', 'Ryzen 5 7600X', 'AMD Ryzen 5 7600X', 'desktop', 'Zen 4', '6', '12', '5.45', 'measured', None, None),
    Row('2410235-NE-285KARROW68', 'Ryzen 5 9600X', 'AMD Ryzen 5 9600X (65 W)', 'desktop', 'Zen 5', '6', '12', '5.48', 'measured', None, None),
    Row('2410235-NE-285KARROW68', 'Ryzen 5 9600X @ 105W cTDP', 'AMD Ryzen 5 9600X @ 105 W cTDP', 'desktop', 'Zen 5', '6', '12', '5.48', 'measured', None, None),
    Row('2410235-NE-285KARROW68', 'Ryzen 7 9700X', 'AMD Ryzen 7 9700X (65 W)', 'desktop', 'Zen 5', '8', '16', '5.50', 'measured', None, ('16.97', '88.17')),
    Row('2410235-NE-285KARROW68', 'Ryzen 7 9700X @ 105W cTDP', 'AMD Ryzen 7 9700X @ 105 W cTDP', 'desktop', 'Zen 5', '8', '16', '5.50', 'measured', None, ('17.99', '133.67')),
    Row('2410235-NE-285KARROW68', 'Ryzen 9 9900X', 'AMD Ryzen 9 9900X', 'desktop', 'Zen 5', '12', '24', '5.66', 'measured', None, None),
    Row('2410235-NE-285KARROW68', 'Ryzen 9 9950X', 'AMD Ryzen 9 9950X', 'desktop', 'Zen 5', '16', '32', '5.75', 'measured', None, ('20.47', '197.30')),
    Row('2410235-NE-285KARROW68', 'Core i9 14900K', 'Intel Core i9-14900K', 'desktop', 'Raptor Cove + Gracemont', '24', '32', '5.70', 'measured', None, ('10.51', '272.33')),
    Row('2410235-NE-285KARROW68', 'Core i9 13900K', 'Intel Core i9-13900K', 'desktop', 'Raptor Cove + Gracemont', '24', '32', '5.50', 'measured', None, ('10.12', '240.90')),
    Row('2410235-NE-285KARROW68', 'Core Ultra 9 285K', 'Intel Core Ultra 9 285K', 'desktop', 'Lion Cove + Skymont', '24', '24', '5.70', 'measured', None, ('12.68', '195.86')),
    Row('2407128-PTS-GRAVITON53', 'Ampere Altra Max 128 Cores', 'Ampere Altra Max M128-30', 'server', 'Neoverse N1', '128', '128', '3.00', 'tdp', '250', None),
    Row('2407128-PTS-GRAVITON53', 'Amazon Graviton4 96 Cores', 'AWS Graviton4', 'server', 'Neoverse V2', '96', '96', '2.80', 'none', '', None),
    Row('2208073-NE-M2REVIEW767', 'Apple Mac Mini - M1', 'Apple M1 (Mac mini)', 'laptop', 'Firestorm + Icestorm', '8', '8', '3.20', 'wall', '26.5', None),
    Row('2208073-NE-M2REVIEW767', 'Apple MacBook Air - M2', 'Apple M2 (MacBook Air)', 'laptop', 'Avalanche + Blizzard', '8', '8', '3.49', 'package_est', '20', None),
]

HEADER = [
    '# Multi-threaded CoreMark 1.0 (pts/coremark, "CoreMark Size 666", gcc -O2) with the CPU package power',
    "# Phoronix's monitor logged during that test (RAPL/sysfs; Min/Avg/Max over the run), from public",
    "# OpenBenchmarking.org result exports. class: server, desktop, laptop. power_kind: measured (PTS monitor),",
    "# wall (AnandTech, whole system), package_est (review estimate), tdp (vendor rating; no measurement).",
]
COLUMNS = [
    "result_id", "class", "cpu", "microarchitecture", "cores", "threads",
    "reported_ghz", "iterations_per_s", "power_w", "power_kind",
    "power_min_w", "power_max_w",
]
PERF_ROW = "Coremark - CoreMark Size 666 - Iterations Per Second (Iterations/Sec)"
POWER_ROW = "Coremark - CPU Power"
PROCESSOR = re.compile(r"@ (?P<ghz>[\d.]+)GHz(?: \((?P<cores>\d+) Cores / (?P<threads>\d+) Threads\))?")


def read_export(text):
    """{system: {perf, power, ghz, cores, threads}} from one PTS CSV export.

    The export is wide -- one column per system, one row per metric -- and
    the systems header is the first blank-titled row that has content.
    """
    rows = list(csv.reader(io.StringIO(text)))
    header = next(
        (r for r in rows
         if r and r[0].strip() == "" and len(r) > 2 and any(c.strip() for c in r[2:])),
        None,
    )
    if header is None:
        raise ValueError("no systems header: this is not a PTS CSV export")
    names = [n.strip() for n in header[2:]]
    out = {n: {} for n in names if n}

    def fill(row, field, convert):
        for name, value in zip(names, row[2:]):
            if name and value.strip():
                out[name][field] = convert(value.strip())

    for row in rows:
        if not row:
            continue
        if row[0].startswith(PERF_ROW):
            fill(row, "perf", float)
        elif row[0].startswith(POWER_ROW):
            fill(row, "power", float)
        elif row[0] == "Processor":
            for name, value in zip(names, row[2:]):
                m = PROCESSOR.search(value or "")
                if name and m:
                    out[name]["ghz"] = m.group("ghz")
                    if m.group("cores"):
                        out[name]["cores"] = m.group("cores")
                        out[name]["threads"] = m.group("threads")
    return out


def build(exports):
    """Render the CSV, and the list of disagreements found on the way."""
    lines, notes = list(HEADER) + [",".join(COLUMNS)], []
    for row in SELECTION:
        export = exports.get(row.result_id)
        if export is None:
            raise SystemExit("missing export %s (%s)"
                             % (row.result_id,
                                SOURCES.get(row.result_id, "not a cited export")))
        system = export.get(row.key)
        if system is None:
            raise SystemExit("%s: no system %r in %s"
                             % (row.cpu, row.key, row.result_id))
        if "perf" not in system:
            raise SystemExit("%s: no CoreMark result in %s" % (row.cpu, row.result_id))

        # measured power comes from the export; anything else is carried,
        # and carrying it when the export HAS a measurement is a mistake
        measured = system.get("power")
        if row.power_kind == "measured":
            if measured is None:
                raise SystemExit("%s: power_kind is measured, export has none" % row.cpu)
            power = "%.2f" % measured
        else:
            if measured is not None:
                notes.append("%s: carried as %s, but the export measured %.2f W"
                             % (row.cpu, row.power_kind, measured))
            power = row.power

        for field, carried in (("cores", row.cores), ("threads", row.threads),
                               ("ghz", row.ghz)):
            found = system.get(field)
            if found is not None and found != carried:
                notes.append("%s: %s carried as %s, export says %s"
                             % (row.cpu, field, carried, found))

        spread = row.spread or ("", "")
        lines.append(",".join([
            row.result_id, row.klass, row.cpu, row.uarch, row.cores, row.threads,
            row.ghz, "%d" % round(system["perf"]), power, row.power_kind,
            spread[0], spread[1],
        ]))
    return "\n".join(lines) + "\n", notes


def load(directory):
    exports = {}
    for result_id in SOURCES:
        path = os.path.join(directory, "%s-result.csv" % result_id)
        if not os.path.exists(path):
            raise SystemExit(
                "missing %s\n  fetch it from https://openbenchmarking.org/result/%s\n"
                "  (%s)" % (path, result_id, SOURCES[result_id]))
        with io.open(path, encoding="utf-8", errors="replace") as f:
            exports[result_id] = read_export(f.read())
    return exports


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--exports", required=True, metavar="DIR",
                   help="directory holding the four <result-id>-result.csv files")
    p.add_argument("--out", metavar="FILE", help="write the CSV here")
    p.add_argument("--check", metavar="FILE",
                   help="compare against this file and fail if it has drifted")
    args = p.parse_args(argv)

    rendered, notes = build(load(args.exports))
    for note in notes:
        sys.stderr.write("note: %s\n" % note)

    if args.check:
        with io.open(args.check, encoding="utf-8") as f:
            committed = f.read()
        if committed != rendered:
            sys.stderr.write(
                "%s does not match the exports; regenerate it with --out\n" % args.check)
            import difflib
            sys.stderr.writelines(difflib.unified_diff(
                committed.splitlines(True), rendered.splitlines(True),
                fromfile="committed", tofile="from exports"))
            return 1
        sys.stderr.write("%s matches the exports (%d rows)\n"
                         % (args.check, len(SELECTION)))
        return 0

    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as f:
            f.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
