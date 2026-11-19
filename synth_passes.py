#!/usr/bin/env python3
"""The slowest yosys passes of each partition of a parallel synthesis.

Reads the partitions' partition_<name>_stat.txt (synth_partition.sh: the
yosys log's timing lines and synth_searches.py's `pass` lines) and
writes, slowest partition first, each partition's wall seconds and its
slowest passes, each with its own wall seconds, its number in the log
(the partition's yosys log, logs/.../partition_<name>.log) and its name:

  1234.5s  MyCore
       900.1s  20 abc
       120.3s  12 extract_fa

  synth_passes.py --out synth_passes.txt STAT...
"""

import argparse
import re

SECTION = re.compile(r"^=== partition (\S+)\s*$")
ELAPSED = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):([\d.]+)")
END_OF_SCRIPT = re.compile(r"End of script\..*\btime: ([\d.]+)s")
PASS = re.compile(r"^pass (\S+) (\S+) seconds=([\d.]+)\s*$")


def read_stats(texts):
    """[(partition, seconds or None, [(seconds, number, name)])]."""
    out = []
    for text in texts:
        row = None
        for line in text.splitlines():
            m = SECTION.match(line)
            if m:
                row = [m.group(1), None, []]
                out.append(row)
                continue
            if row is None:
                continue
            m = PASS.match(line)
            if m:
                row[2].append((float(m.group(3)), m.group(1), m.group(2)))
                continue
            m = ELAPSED.search(line)
            if m:
                row[1] = (
                    int(m.group(1) or 0) * 3600
                    + int(m.group(2)) * 60
                    + float(m.group(3))
                )
                continue
            m = END_OF_SCRIPT.search(line)
            if m and row[1] is None:
                row[1] = float(m.group(1))
    return [tuple(r) for r in out]


def report(stats):
    lines = []
    for name, seconds, passes in sorted(stats, key=lambda r: (-(r[1] or 0.0), r[0])):
        total = "?" if seconds is None else f"{seconds:.1f}s"
        lines.append(f"{total:>9}  {name}")
        for pass_seconds, number, pass_name in passes:
            lines.append(f"    {pass_seconds:>9.1f}s  {number} {pass_name}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("stats", nargs="*")
    args = parser.parse_args(argv)
    texts = []
    for path in args.stats:
        with open(path) as f:
            texts.append(f.read())
    with open(args.out, "w") as f:
        f.writelines(line + "\n" for line in report(read_stats(texts)))


if __name__ == "__main__":
    main()
