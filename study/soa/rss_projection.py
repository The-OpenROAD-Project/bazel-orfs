#!/usr/bin/env python3
"""Project the in-memory saving of field-major storage for one design.

Inputs are measured, not assumed:
  * slot counts per table, from the SoaDumpTable dumps
  * per-slot layouts, from SoaLayoutFacts against the same OpenROAD revision
  * the design's actual peak RSS, from read_db_cost.sh, minus the RSS of the
    same binary loading nothing -- so the figure is the design's footprint,
    not the process's

What it does NOT do is claim the saving as measured: it is what the layouts
say the tables must give up, applied to the tables this design has. The
prototype's own RSS is what settles it.

The figure is deliberately conservative in one way worth stating. It counts
in-slot bytes only. On a routed design most iterms carry an access point, and
`aps_` is a boost flat_map, so each of those slots also owns a small heap
allocation that today's `sizeof` does not show. Consolidating them into one
side table reclaims that too, and none of it is in the number below.
"""

import argparse
import csv
import json
from pathlib import Path

# sizeof -> bytes a field-major slot still needs, measured per revision.
# The difference is derivable bookkeeping, padding, the Rect/Oct union's
# unused 4 bytes, and (iterm only) an access-point map that is empty on most
# slots and becomes a sparse side table.
PER_SLOT = {
    "sbox": (52, 40),
    "box": (48, 36),
    "iterm": (88, 48),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump-stem", required=True, help="e.g. tmp/dump/ariane")
    parser.add_argument("--tables", default="sbox,box,iterm")
    parser.add_argument("--readdb-csv", required=True)
    parser.add_argument("--baseline-rss-kb", type=float, required=True)
    args = parser.parse_args()

    rows = list(csv.DictReader(open(args.readdb_csv)))
    peak_kb = min(float(r["peak_rss_kb"]) for r in rows)
    design_kb = peak_kb - args.baseline_rss_kb

    # Record lengths say how many slots carry variable-length payload -- for
    # iterm that is the access-point map, which only exists after pin access.
    occupancy = {}
    for table in args.tables.split(","):
        meta = json.loads(Path(f"{args.dump_stem}.{table}.json").read_text())
        lengths = meta["lengths"]
        if lengths:
            shortest = min(lengths)
            carrying = sum(1 for value in lengths if value != shortest)
            occupancy[table] = carrying / len(lengths)

    total_now = total_after = 0
    print(
        f"{'table':8s} {'slots':>10s} {'now MB':>9s} {'after MB':>9s} {'saved MB':>9s}"
    )
    for table in args.tables.split(","):
        meta = json.loads(Path(f"{args.dump_stem}.{table}.json").read_text())
        slots = meta["slots"]
        now, after = PER_SLOT[table]
        a, b = slots * now / 1e6, slots * after / 1e6
        total_now, total_after = total_now + a, total_after + b
        print(f"{table:8s} {slots:>10,d} {a:>9.1f} {b:>9.1f} {a - b:>9.1f}")

    for table, share in occupancy.items():
        if share:
            print(
                f"note: {100 * share:.1f}% of {table} records are longer than the "
                f"shortest, so they carry payload a side table absorbs"
            )

    saved = total_now - total_after
    print(f"{'total':8s} {'':>10s} {total_now:>9.1f} {total_after:>9.1f} {saved:>9.1f}")
    print()
    print(f"peak RSS loading the design : {peak_kb / 1024:8.1f} MB")
    print(f"same binary loading nothing : {args.baseline_rss_kb / 1024:8.1f} MB")
    print(f"the design's own footprint  : {design_kb / 1024:8.1f} MB")
    print(
        f"these tables are            : {100 * total_now / (design_kb / 1024):8.1f}% of it"
    )
    print(
        f"projected saving            : {saved:8.1f} MB, "
        f"{100 * saved / (design_kb / 1024):.1f}% of the design's footprint"
    )


if __name__ == "__main__":
    main()
