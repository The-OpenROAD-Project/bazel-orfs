#!/usr/bin/env python3
"""Why field-major byte order compresses: what the columns actually contain.

A slot's serialized record is a row of fixed-width fields. Read as columns,
most of them turn out to be constant or monotone -- an unused hierarchy id,
a flag word with a handful of values, an object id that climbs with the slot
index. Array-of-structs interleaves those columns with the two or three
high-entropy ones, so no compressor sees a run longer than a field.

This prints, per 4-byte column of a table's records: how many distinct
values it holds, and how often its first difference is constant. Columns
with one distinct value cost nothing at all once transposed; columns with a
constant delta cost almost nothing. That is the whole mechanism, and it says
which designs gain most rather than leaving the spread unexplained.

Only tables whose records are all one length are analysed -- after pin
access, iterm records come in two lengths and want splitting by class first.
"""

import argparse
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stems", nargs="+", help="dump stems, without .bin/.json")
    args = parser.parse_args()

    for stem in args.stems:
        meta = json.loads(Path(stem + ".json").read_text())
        lengths = meta["lengths"]
        width = min(lengths)
        if max(lengths) != width:
            print(f"{stem}: records come in {len(set(lengths))} lengths, skipped")
            continue
        if width % 4:
            print(f"{stem}: record length {width} is not a whole number of words")
            continue

        rows = np.fromfile(stem + ".bin", dtype=np.uint8).reshape(-1, width)
        words = rows.view(np.uint32)
        print(f"\n{stem}  table={meta['table']}  records={words.shape[0]:,} "
              f"columns={words.shape[1]}")
        constant = 0
        for column in range(words.shape[1]):
            values = words[:, column].astype(np.int64)
            deltas = np.diff(values)
            same = 100 * float(np.mean(deltas == deltas[0])) if deltas.size else 100.0
            distinct = len(np.unique(values))
            constant += distinct == 1
            print(f"   col{column:<2d} distinct={distinct:>9,d} constant-delta={same:5.1f}%")
        print(f"   -> {constant} of {words.shape[1]} columns hold a single value")


if __name__ == "__main__":
    main()
