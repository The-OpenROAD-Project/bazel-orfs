#!/usr/bin/env python3
"""Replaying each shard's netlist from one RTL capture measures what the
all-gates simulation does, and catches a netlist that is not its RTL.

  - the capture simulation (the RTL, each unit behind a wrapper of its
    ports) computes what the RTL does: its outputs are the all-RTL run's;
  - the SAIF merged from the replays is the all-gates SAIF net for net
    (durations and toggle counts), every net of the parent's netlist and
    of every block's included;
  - cutting BlockC into two simulation shards (u_core on its own, the
    rest with it cut out) gives the same merged SAIF as replaying it
    whole, from the capture and in two levels (u_core replayed from the
    stub's ports BlockC's replay recorded, two_level);
  - every power shard comes out the same from the replays' SAIF as from
    the all-gates one;
  - a capture with one input bit flipped, and a netlist with one gate
    inverted, each fail the replay at the cycle the difference reaches
    an output, naming the output;
  - two levels: a capture of the parent's boundary alone, the parent's
    RTL replayed from it recording its units' ports, gives every unit
    the same SAIF as the one-level capture.

Equal, not within a tolerance: zero-delay, two-state simulation on both
sides, sampled at the same times.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mixed_test import nets  # noqa: E402

ARGS = None


def under(saif, prefix):
    n = len(prefix) + 1
    return {k[n:]: v for k, v in nets(saif).items() if k.startswith(prefix + "/")}


def read(path):
    with open(path) as f:
        return f.read()


def replay(binary, vcd):
    d = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
    return subprocess.run(
        [binary, vcd, os.path.join(d, "o.saif"), "16000", "1000"],
        capture_output=True,
        text=True,
    )


class ReplayTest(unittest.TestCase):
    def test_capture_computes_what_the_rtl_does(self):
        self.assertEqual(read(ARGS.capture_out), read(ARGS.rtl_out))

    def test_replayed_is_the_all_gates_saif(self):
        gates = under(ARGS.all_gates, "TOP/mini_top")
        replayed = under(ARGS.replayed, "TOP/replayed_parent/dut")
        self.assertEqual(sorted(replayed), sorted(gates))
        differ = [k for k in gates if gates[k] != replayed[k]]
        print(
            "replayed vs all-gates: {} nets, {} differ".format(len(gates), len(differ))
        )
        self.assertEqual(differ[:10], [])

    def test_cut_is_the_whole(self):
        whole = under(ARGS.replayed, "TOP/replayed_parent/dut")
        cut = under(ARGS.cut, "TOP/replayed_cut_parent/dut")
        self.assertEqual(cut, whole)
        inside = [k for k in cut if k.startswith("u_blockc/u_core/")]
        print("BlockC's u_core, replayed on its own: {} nets".format(len(inside)))
        self.assertGreater(len(inside), 100)

    def test_cut_in_two_levels_is_the_whole(self):
        whole = under(ARGS.replayed, "TOP/replayed_parent/dut")
        cut = under(ARGS.cut2, "TOP/replayed_cut2_parent/dut")
        self.assertEqual(cut, whole)

    def test_shards_the_same(self):
        n = len(ARGS.shards) // 2
        for a, b in zip(ARGS.shards[:n], ARGS.shards[n:]):
            a, b = json.loads(read(a)), json.loads(read(b))
            self.assertEqual(a["unit"], b["unit"])
            self.assertEqual(a["annotation"], b["annotation"])
            self.assertEqual(
                a["vector_driven"]["design"], b["vector_driven"]["design"], a["unit"]
            )

    def test_flipped_capture_bit_caught(self):
        text = read(ARGS.capture)
        var = re.search(
            r"\$var wire\s+\d+\s+(\S+)\s+din \[99:0\] \$end",
            text[: text.index("$enddefinitions")],
        )
        # the block's din, in u_blockc's wrapper scope
        header = text[: text.index("$enddefinitions")]
        scope = header[: var.start()].split("$scope module u_blockc $end")
        self.assertGreater(len(scope), 1)
        ident = var.group(1)
        cycle = 1000
        t = "#{}\n".format((2 * cycle + 1) * 500)
        at = text.index(t) + len(t)
        end = text.index("#", at)
        block = text[at:end]
        m = re.search(r"^b([01]+) " + re.escape(ident) + r"$", block, re.M)
        self.assertIsNotNone(m)
        bits = m.group(1)
        flipped = bits[:-1] + ("0" if bits[-1] == "1" else "1")
        bad = text[: at + m.start(1)] + flipped + text[at + m.end(1) :]
        path = os.path.join(
            tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")), "c.vcd"
        )
        with open(path, "w") as f:
            f.write(bad)
        result = replay(ARGS.blockc_bin, path)
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        found = re.search(
            r"TOP\.mini_top\.rtl\.u_blockc\.dout differs at cycle (\d+)", result.stderr
        )
        self.assertIsNotNone(found, result.stderr)
        self.assertIn(int(found.group(1)), range(cycle, cycle + 3))

    def test_inverted_gate_caught(self):
        self.assertEqual(replay(ARGS.blockc_bin, ARGS.capture).returncode, 0)
        result = replay(ARGS.bad_bin, ARGS.capture)
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertRegex(
            result.stderr,
            r"u_blockc\.dout differs at cycle \d+ \(time \d+, clock (low|high)\)",
        )


class TwoLevelTest(unittest.TestCase):
    def test_units_replayed_from_the_parents_replay(self):
        for spec in ARGS.block:
            unit, binary, direct = spec.split("=")
            d = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
            out = os.path.join(d, "o.saif")
            result = subprocess.run(
                [
                    binary,
                    ARGS.relayed,
                    out,
                    "16000",
                    "1000",
                    "0",
                    "TOP.mini_top=TOP.relay_mini_top.dut",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(nets(out), nets(direct), unit)
        print("two levels: {} units' SAIFs the same".format(len(ARGS.block)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for k in (
        "all_gates",
        "replayed",
        "cut",
        "cut2",
        "capture",
        "capture_out",
        "rtl_out",
        "blockc_bin",
        "bad_bin",
        "relayed",
    ):
        parser.add_argument("--" + k.replace("_", "-"), dest=k, required=True)
    parser.add_argument("--shards", action="append", default=[])
    parser.add_argument("--block", action="append", default=[])
    ARGS = parser.parse_args()
    unittest.main(argv=sys.argv[:1])
