#!/usr/bin/env python3
"""What a synthesis spent on its searches, and what they found.

Reads yosys's full log as yosys writes it (`yosys -l FIFO`, filtered
by synth_partition.sh to the lines read here) and, at its end, writes to
OUT the passes a partition can turn off for itself
(partition_arguments), each with its wall seconds and yield:

  search extract_fa seconds=12.3 full=10 half=4
  search share seconds=3.1 candidates=40 merged=2
  search abc seconds=100.2

A pass that did not run has no line. The yields are in the full log
only: ORFS runs yosys with -v 3, which keeps all but the headers out of
its own log. Seconds are wall time, stamped as each pass's header
arrives: yosys flushes its log at every header, so a pass lasts from its
header to the next header at its depth or above (or the end of the
log). yosys's own `Time spent` is CPU time, and counts one abc under the
Tcl frontend as two calls.
"""

import re
import sys
import time

HEADER = re.compile(rb"^(\d+(?:\.\d+)*)\. Executing (\S+) pass")
ABC_PASSES = {b"ABC", b"ABC9", b"ABC_NEW"}
FA_SECTION = re.compile(rb"^\s+([23])-Input XOR/XNOR ")
FA_CREATED = re.compile(rb"^\s+Created \$fa cell ")
SHARE_FOUND = re.compile(
    rb"^Found (\d+) cells in module .* may be considered for resource sharing\."
)
SHARE_MERGED = re.compile(rb"^\s+New cell: ")


class Searches:
    """Fed the output's lines with their arrival times, sums up the
    searches."""

    def __init__(self):
        self.open = []  # [depth, name, start] of passes not yet ended
        self.seconds = {}
        self.counts = {"full": 0, "half": 0, "candidates": 0, "merged": 0}
        self.section = None

    def _close(self, depth, t):
        while self.open and self.open[-1][0] >= depth:
            _, name, start = self.open.pop()
            if name is None or (
                name == "abc" and any(n == "abc" for _, n, _ in self.open)
            ):
                continue
            self.seconds[name] = self.seconds.get(name, 0.0) + t - start

    def feed(self, line, t):
        m = HEADER.match(line)
        if m:
            depth = m.group(1).count(b".") + 1
            self._close(depth, t)
            name = m.group(2)
            if name == b"EXTRACT_FA":
                self.open.append([depth, "extract_fa", t])
            elif name == b"SHARE":
                self.open.append([depth, "share", t])
            elif name in ABC_PASSES:
                self.open.append([depth, "abc", t])
            else:
                self.open.append([depth, None, t])
            self.section = None
            return
        inside = {n for _, n, _ in self.open}
        if "extract_fa" in inside:
            s = FA_SECTION.match(line)
            if s:
                self.section = "full" if s.group(1) == b"3" else "half"
            elif self.section and FA_CREATED.match(line):
                self.counts[self.section] += 1
        elif "share" in inside:
            s = SHARE_FOUND.match(line)
            if s:
                self.counts["candidates"] += int(s.group(1))
            elif SHARE_MERGED.match(line):
                self.counts["merged"] += 1

    def end(self, t):
        self._close(0, t)

    def lines(self):
        out = []
        c = self.counts
        if "extract_fa" in self.seconds:
            out.append(
                f"search extract_fa seconds={self.seconds['extract_fa']:.1f} "
                f"full={c['full']} half={c['half']}"
            )
        if "share" in self.seconds:
            out.append(
                f"search share seconds={self.seconds['share']:.1f} "
                f"candidates={c['candidates']} merged={c['merged']}"
            )
        if "abc" in self.seconds:
            out.append(f"search abc seconds={self.seconds['abc']:.1f}")
        return out


def main(argv):
    searches = Searches()
    for line in iter(sys.stdin.buffer.readline, b""):
        searches.feed(line, time.monotonic())
    searches.end(time.monotonic())
    with open(argv[0], "w") as f:
        f.writelines(line + "\n" for line in searches.lines())


if __name__ == "__main__":
    main(sys.argv[1:])
