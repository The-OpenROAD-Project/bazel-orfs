#!/usr/bin/env python3
"""One simulation per shard measures what the all-gates simulation does.

The shards' SAIF is merged (scripts/saif_merge.py) from the parent's
simulation (its netlist, the blocks RTL) and each block's (the RTL, that
block alone its netlist, its scope alone traced). The proof that this is
the same measurement as one simulation with every unit as gates, on the
same stimulus:

  - every simulation's outputs, cycle by cycle, are the all-RTL one's: a
    unit's gates behave as its RTL, the functional gate a mixed
    simulation must pass to count;
  - the merged SAIF is the all-gates SAIF net for net, durations and
    toggle counts, inside the blocks and outside them, BlockB's bridged
    second clock pin (clock_ext) included;
  - each block's ports, the nets that cross its boundary, toggle the same
    captured from its RTL (the parent's simulation) and from its gates
    (the all-gates one): RTL and gates agree at the boundary, sampled
    as a SAIF samples them, twice a cycle;
  - so each shard and the sum come out the same from either SAIF.

Zero-delay simulation has no glitches on either side, so equal outputs
and equal boundary toggles are exact, not within a tolerance; the
shards are compared to report_power's printed digits.
"""

import argparse
import json
import os
import re
import sys
import unittest

ARGS = None


def nets(path):
    """{net path: (T0, T1, TC)} of a SAIF."""
    out = {}
    stack = []
    depth = 0
    with open(path) as f:
        for line in f:
            m = re.match(r"^\s*\(INSTANCE\s+(\S+)", line)
            if m:
                stack.append((m.group(1), depth))
            else:
                n = re.match(
                    r"^\s*\((\S+)\s+\(T0 (\d+)\)\s+\(T1 (\d+)\).*\(TC (\d+)\)\)", line
                )
                if n:
                    scope = "/".join(s for s, _ in stack)
                    out[scope + "/" + n.group(1)] = (n.group(2), n.group(3), n.group(4))
            depth += line.count("(") - line.count(")")
            while stack and depth <= stack[-1][1]:
                stack.pop()
    return out


def read(path):
    with open(path) as f:
        return f.read()


class MixedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all_gates = nets(ARGS.all_gates)
        cls.merged = nets(ARGS.merged)

    def test_outputs_are_the_rtl_outputs(self):
        rtl = read(ARGS.rtl_out)
        self.assertGreater(len(rtl.splitlines()), 1000)
        for path in ARGS.out:
            with self.subTest(sim=os.path.basename(path)):
                self.assertEqual(read(path), rtl)

    def test_merged_is_the_all_gates_saif(self):
        self.assertEqual(sorted(self.merged), sorted(self.all_gates))
        differ = [p for p in self.all_gates if self.merged[p] != self.all_gates[p]]
        print(
            "merged vs all-gates: {} nets, {} differ".format(
                len(self.all_gates), len(differ)
            )
        )
        self.assertEqual(differ[:10], [])
        for block in ARGS.block:
            inside = [
                p
                for p in self.merged
                if p.startswith("{}/{}/".format(ARGS.scope, block))
            ]
            self.assertGreater(len(inside), 1000, block)
        self.assertIn("{}/u_blockb/clock_ext".format(ARGS.scope), self.merged)

    def test_boundary_toggles_rtl_side_equal_gate_side(self):
        parent = nets(ARGS.parent)
        compared = 0
        for block in ARGS.block:
            prefix = "{}/{}/".format(ARGS.scope, block)
            ports = [
                p
                for p in self.all_gates
                if p.startswith(prefix) and "/" not in p[len(prefix) :]
            ]
            for p in ports:
                if p in parent:
                    compared += 1
                    self.assertEqual(parent[p], self.all_gates[p], p)
        print("boundary nets compared, RTL side against gate side: {}".format(compared))
        self.assertGreater(compared, 900)

    def test_shards_and_sum_the_same_from_either_saif(self):
        n = len(ARGS.shards) // 2
        for one, merged in zip(ARGS.shards[:n], ARGS.shards[n:]):
            a, b = json.loads(read(one)), json.loads(read(merged))
            self.assertEqual(a["unit"], b["unit"])
            self.assertEqual(a["annotation"], b["annotation"])
            self.assertEqual(
                a["vector_driven"]["design"], b["vector_driven"]["design"], a["unit"]
            )
        a, b = (json.loads(read(p))["Total"] for p in ARGS.sum)
        self.assertEqual(a, b)

    def test_scoped_capture_is_smaller(self):
        scoped, whole = os.path.getsize(ARGS.scoped), os.path.getsize(ARGS.whole)
        print("BlockB's own SAIF: {} bytes scoped, {} whole".format(scoped, whole))
        self.assertLess(scoped, whole / 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for k in ("all_gates", "merged", "parent", "scoped", "whole", "rtl_out", "scope"):
        parser.add_argument("--" + k.replace("_", "-"), dest=k, required=True)
    for k in ("out", "shards", "sum", "block"):
        parser.add_argument("--" + k, action="append", default=[])
    ARGS = parser.parse_args()
    unittest.main(argv=sys.argv[:1])
