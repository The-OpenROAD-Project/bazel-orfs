#!/usr/bin/env python3
"""Graft each hardened unit's gate-level SAIF into its parent's.

    saif_merge.py --parent PARENT.saif --out MERGED.saif
                  [--unit TARGET=UNIT.saif:SOURCE]... [--clock NAME]...

The power of a hierarchical design is measured in shards, one per unit
(flow/power.bzl's stage_power_shards), each reading one SAIF at its own
scope. That SAIF is made from one simulation per unit instead of one with
every unit as gates: the parent's (its netlist as gates, every hardened
unit as RTL) and each unit's (the SoC's RTL with that unit alone as its
own gate netlist). This writes the parent's SAIF with each unit's RTL
subtree replaced by the unit's gate-level subtree from its own SAIF.

  TARGET   where the unit goes in the merged file: the path of the
           instance whose subtree is replaced. It is where the netlist
           that holds the unit has it, which is where the unit's parent
           shard finds it, its names as that netlist spells them: a
           level the netlist flattened is part of one instance name
           (`a__SL__b`, scripts/slash_names.py), not a scope.
  SOURCE   the unit's path in its own SAIF: its RTL instance path, every
           level a scope.

A nested unit (a register file inside a block) is grafted the same way,
its TARGET inside its block's TARGET; its subtree replaces the RTL one
that the block's own simulation has there.

Refused, by name, when the files cannot be one measurement: a DIVIDER,
TIMESCALE or DURATION that differs from the parent's, a TARGET that is
absent from the file it goes into or is given twice, a unit whose SAIF
lacks its SOURCE, and a clock that differs: the design has one clock,
so every net named by --clock (the clock ports, `clock`, and any a
flow split it into) at the top two levels of each file and at the root
of each unit, in the parent's RTL and in the unit's gates, must have the
same durations and toggle count. Below a unit's root a net of that name
may be a gated clock, and is not compared.

Streaming: each file is read once, line by line, and only a unit's own
subtree is kept from its file, so a per-unit capture limited to its own
scope is all the merge needs. The line structure is Verilator's SAIF
writer's: one `(INSTANCE name` per line, one net per line.
"""

import argparse
import re
import sys

_INSTANCE = re.compile(r"^\s*\(INSTANCE\s+(\S+)")
_NET = re.compile(r"^\s*\((\S+)\s+(\(T0 .*)\)\s*$")
_HEADER = re.compile(r"^\s*\((DIVIDER|TIMESCALE|DURATION)\s+(.*?)\s*\)\s*$")


def _depth(line):
    return line.count("(") - line.count(")")


class Saif:
    """A SAIF file read once, its lines with their instance paths."""

    def __init__(self, path, clocks=(), watch=()):
        self.path = path
        self.f = open(path, errors="replace")
        self.header = {}
        self.head = []
        self.clocks = set(clocks)
        self.watch = set(watch)
        self.clock_values = []
        self.pending = None
        self._stack = []  # (name, depth it opened at)
        self._depth = 0
        while True:
            line = self.f.readline()
            if not line or _INSTANCE.match(line):
                self.pending = line
                break
            self.head.append(line)
            self._depth += _depth(line)
            m = _HEADER.match(line)
            if m:
                self.header[m.group(1)] = m.group(2)

    def scope(self):
        return "/".join(n for n, _ in self._stack)

    def lines(self):
        """(line, path of the instance it opens or None, path it is in)."""
        while True:
            if self.pending is not None:
                line, self.pending = self.pending, None
            else:
                line = self.f.readline()
            if not line:
                return
            m = _INSTANCE.match(line)
            opened = None
            if m:
                self._stack.append((m.group(1), self._depth))
                opened = self.scope()
            elif self.clocks:
                n = _NET.match(line)
                if n and n.group(1) in self.clocks:
                    scope = self.scope()
                    if scope.count("/") < 2 or scope in self.watch:
                        self.clock_values.append(
                            (
                                "{}:{}/{}".format(self.path, scope, n.group(1)),
                                n.group(2),
                            )
                        )
            self._depth += _depth(line)
            while self._stack and self._depth <= self._stack[-1][1]:
                self._stack.pop()
            yield line, opened, self.scope()

    def skip_subtree(self, lines):
        """Consume the rest of the subtree just opened."""
        floor = len(self._stack) - 1
        if len(self._stack) <= floor:
            return
        for _ in lines:
            if len(self._stack) <= floor:
                return

    def close(self):
        self.f.close()


def _rename(line, name):
    m = _INSTANCE.match(line)
    return line[: m.start(1)] + name + line[m.end(1) :]


class Merge:
    def __init__(self, parent, units, out, clocks=()):
        """units: [(target, saif path, source)]."""
        self.out = out
        self.clocks = clocks
        targets = [t for t, _, _ in units]
        dup = sorted({t for t in targets if targets.count(t) > 1})
        if dup:
            raise ValueError("a unit's place given twice: {}".format(", ".join(dup)))
        self.units = {t: (p, s) for t, p, s in units}
        self.grafted = set()
        self.clock_values = []
        self.parent = Saif(parent, clocks, targets)

    def _check_header(self, saif):
        for key in ("DIVIDER", "TIMESCALE", "DURATION"):
            if saif.header.get(key) != self.parent.header.get(key):
                raise ValueError(
                    "{}: {} {} against the parent's {}".format(
                        saif.path,
                        key,
                        saif.header.get(key),
                        self.parent.header.get(key),
                    )
                )

    def _copy(self, saif, lines, root_source, root_target):
        """Copy the subtree just opened in `saif`, at root_target, grafting
        any unit whose target falls inside it."""
        floor = len(saif._stack) - 1
        for line, opened, _ in lines:
            if len(saif._stack) <= floor and opened is None:
                self.out.write(line)
                return
            if opened is not None:
                target = root_target + opened[len(root_source) :]
                if target in self.units:
                    saif.skip_subtree(lines)
                    self._graft(target)
                    continue
            self.out.write(line)

    def _graft(self, target):
        if target in self.grafted:
            raise ValueError("{}: found twice".format(target))
        self.grafted.add(target)
        path, source = self.units[target]
        unit = Saif(path, self.clocks, [source])
        self._check_header(unit)
        lines = unit.lines()
        for line, opened, _ in lines:
            if opened == source:
                self.out.write(_rename(line, target.rsplit("/", 1)[-1]))
                self._copy(unit, lines, source, target)
                break
        else:
            raise ValueError("{}: no instance {}".format(path, source))
        self.clock_values += unit.clock_values
        unit.close()

    def run(self):
        self.out.write("".join(self.parent.head))
        lines = self.parent.lines()
        for line, opened, _ in lines:
            if opened is not None and opened in self.units:
                self.parent.skip_subtree(lines)
                self._graft(opened)
                continue
            self.out.write(line)
        self.clock_values = self.parent.clock_values + self.clock_values
        self.parent.close()
        absent = sorted(set(self.units) - self.grafted)
        if absent:
            raise ValueError(
                "no instance {} in the file it goes into".format(", ".join(absent))
            )
        if self.clocks:
            seen = self.clock_values
            if not seen:
                raise ValueError("no file has a clock net {}".format(self.clocks))
            for p, v in seen[1:]:
                if v != seen[0][1]:
                    raise ValueError(
                        "the clock differs: {} at {}, {} at {}".format(
                            seen[0][1], seen[0][0], v, p
                        )
                    )


def parse_unit(spec):
    target, rest = spec.split("=", 1)
    path, source = rest.rsplit(":", 1)
    return target, path, source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--parent", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--unit", action="append", default=[], type=parse_unit)
    parser.add_argument(
        "--clock", action="append", default=[], help="a clock net's name (repeatable)"
    )
    args = parser.parse_args(argv)
    try:
        with open(args.out, "w") as out:
            Merge(args.parent, args.unit, out, args.clock).run()
    except ValueError as e:
        sys.stderr.write("saif_merge: {}\n".format(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
