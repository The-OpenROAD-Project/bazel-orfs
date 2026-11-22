#!/usr/bin/env python3
"""A kept module with punched ports, replayed in two levels, measures what
replaying its unit whole does, and checks the module against its RTL.

Punched (punched.sv) has PunCore kept; its hand-made netlist
(punched_netlist.v) has two inputs its RTL lacks, fed back in from
buffers in the parent, one from PunCore's own output q[0], one from its
sibling PunIn's q[2], and lacks PunCore's unused input `en`. The capture
cannot drive the punched inputs, so u_core is replayed in two levels
(scripts/replay_gen.py):

  - level 1, the rest of Punched with u_core a stub, records every port
    of the stub: its outputs are the capture's, its RTL inputs are
    checked against the capture as ever, its punched inputs are what the
    netlist drives them with;
  - level 2 replays u_core from that, its outputs checked against the
    stub's, which are the RTL capture's: PunCore's netlist behaves as its
    RTL, the punched ports included;
  - the SAIF merged from the two levels is the whole unit's replay net
    for net (durations and toggle counts), so its power is too: a power
    report reads the netlist, the parasitics and these numbers alone;
  - driven with a punched port's value a cycle stale, or with two
    punched ports' aliases swapped, level 2 fails, naming u_core's
    output and the cycle;
  - the bits the netlist fixes on its own are not compared, decided
    from the netlist when the replay is generated: PunCore's mode, a
    register its RTL only ever writes 2'b10 and never writes in this run,
    tie cells in the netlist and 0 in the capture, at level 2; the bit
    of PunCore's unused input tag that the parent's netlist leaves
    undriven, at level 1. Each passes and is listed; the same difference
    on a bit a cell drives (q, tag[0]) fails at the first time it shows;
  - the pins the unit drives into the stub are the unit's internal nets,
    compared with the RTL's and reported, not required to match: a
    netlist whose data[0] differs only while PunCore's v is 0 passes
    both levels, listed at level 1; one whose data[0] differs while v is
    1 is listed at level 1 and fails level 2 at PunCore's output acc;
    --strict-stub-inputs makes either fatal at level 1. The unit's own
    outputs differing fail level 1;
  - level 1's stub drives mode with the netlist's constant, not the
    capture's 0: the parent's buffer on mode[1] toggles as in the whole
    unit's replay, which the equality above includes.

Equal, not within a tolerance: zero-delay, two-state simulation on both
sides, sampled at the same times (replay_test.py's cut test is the same
comparison for a cut whose ports match).
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
PERIOD = 1000
LEVEL1 = "TOP.punched_cut_parent.dut.u_core"


def under(saif, prefix):
    n = len(prefix) + 1
    return {k[n:]: v for k, v in nets(saif).items() if k.startswith(prefix + "/")}


def read(path):
    with open(path) as f:
        return f.read()


def vcd_values(path, signals):
    """{dotted name: [(time, value bits)]} of a VCD, for `signals`."""
    text = read(path)
    head, body = text.split("$enddefinitions", 1)
    ids = {}
    scope = []
    for line in head.splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "$scope":
            scope.append(tok[2])
        elif tok[0] == "$upscope":
            scope.pop()
        elif tok[0] == "$var":
            full = ".".join(scope + [tok[4]])
            if full in signals:
                ids.setdefault(tok[3], []).append(full)
    out = {s: [] for s in signals}
    t = 0
    for line in body.splitlines()[1:]:
        if not line or line[0] == "$":
            continue
        if line[0] == "#":
            t = int(line[1:])
            continue
        if line[0] in "bB":
            bits, ident = line[1:].split()
        else:
            bits, ident = line[0], line[1:]
        for s in ids.get(ident, []):
            out[s].append((t, int(bits, 2)))
    return out


def replay(vcd):
    d = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
    return subprocess.run(
        [ARGS.level2_bin, vcd, os.path.join(d, "o.saif"), "16000", str(PERIOD)],
        capture_output=True,
        text=True,
    )


def write(text):
    path = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")), "s.vcd")
    with open(path, "w") as f:
        f.write(text)
    return path


def ident(head, name):
    m = re.search(r"^\$var wire \d+ (\S+) " + re.escape(name) + r" ", head, re.M)
    return m.group(1)


def scoped_ident(head, dotted):
    """The id code of the VCD variable at `dotted` (scopes, then name)."""
    scope = []
    for line in head.splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "$scope":
            scope.append(tok[2])
        elif tok[0] == "$upscope":
            scope.pop()
        elif tok[0] == "$var" and ".".join(scope + [tok[4]]) == dotted:
            return tok[3]
    raise KeyError(dotted)


def flip_bit(text, dotted, bit):
    """A VCD with bit `bit` of the vector `dotted` inverted at every
    change. A VCD names one id code for every variable of the same value
    (Verilator's capture: a unit's output and its child's, an input and
    the net it comes from): `dotted` gets an id of its own first, so only
    it changes."""
    head, body = text.split("$enddefinitions", 1)
    code = scoped_ident(head, dotted)
    own = "~flip~"
    scope, lines = [], []
    for line in head.split("\n"):
        tok = line.split()
        if tok[:1] == ["$scope"]:
            scope.append(tok[2])
        elif tok[:1] == ["$upscope"]:
            scope.pop()
        elif tok[:1] == ["$var"] and ".".join(scope + [tok[4]]) == dotted:
            tok[3] = own
            line = " ".join(tok)
        lines.append(line)
    head = "\n".join(lines)
    out = []
    for line in body.split("\n"):
        out.append(line)
        if line[:1] in ("b", "B") and line.split()[1] == code:
            bits = list(line[1:].split()[0].rjust(bit + 1, "0"))
            k = len(bits) - 1 - bit
            bits[k] = "0" if bits[k] == "1" else "1"
            out.append("b" + "".join(bits) + " " + own)
    return head + "$enddefinitions" + "\n".join(out)


def run(binary, vcd, *flags):
    d = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
    return subprocess.run(
        [binary, vcd, os.path.join(d, "o.saif"), "16000", str(PERIOD)] + list(flags),
        capture_output=True,
        text=True,
    )


def level1(vcd, *flags):
    return run(ARGS.level1_bin, vcd, *flags)


DATA = "TOP.Punched.rtl.u_core.data"
NONE_DIFFER = (
    "replay: stub inputs differing from the RTL: 0 signals, 0 cycles; not "
    "required to match, each piece's outputs are (level 2)"
)


class PunchedTest(unittest.TestCase):
    def test_level1_records_the_punched_ports(self):
        stub = json.loads(read(ARGS.stubs_json))["u_core"]
        self.assertEqual(stub["scope"], LEVEL1)
        self.assertEqual(stub["punched"], {"\\u_in.q_2_": "pp_0", "net7_0": "pp_1"})
        self.assertEqual(stub["dropped"], ["en"])
        report = json.loads(read(ARGS.level2_report))
        self.assertEqual(report["punched"], stub["punched"])
        self.assertEqual(report["dropped"], ["en"])

    def test_stub_outputs_are_the_rtl_capture(self):
        # what level 2 checks u_core's outputs against
        rtl = "TOP.Punched.rtl.u_core."
        got = vcd_values(ARGS.stubs_vcd, [LEVEL1 + ".q", LEVEL1 + ".d"])
        want = vcd_values(ARGS.capture, [rtl + "q", rtl + "d"])
        for port in ("q", "d"):
            a, b = got[LEVEL1 + "." + port], want[rtl + port]
            self.assertGreater(len(b), 100, port)
            # the capture dumps only changes, the stubs VCD at its first
            # time all: the same values at the same times
            final = lambda v: dict(v)  # noqa: E731
            self.assertEqual(final(a), final(b), port)

    def test_punched_ports_carry_the_netlists_nets(self):
        # net7_0 is q[0] through two buffers, \u_in.q_2_ is d[2]
        v = vcd_values(
            ARGS.stubs_vcd,
            [LEVEL1 + "." + s for s in ("q", "d", "pp_0", "pp_1")],
        )
        step = lambda s: dict(v[LEVEL1 + "." + s])  # noqa: E731
        q, d, pp0, pp1 = step("q"), step("d"), step("pp_0"), step("pp_1")

        def at(series, t):
            return series[max(k for k in series if k <= t)]

        times = sorted(set(q) | set(d) | set(pp0) | set(pp1))
        # they change at rising edges alone: about one time in two
        self.assertGreater(len(times), 150)
        for t in times:
            self.assertEqual(at(pp1, t), at(q, t) & 1, t)
            self.assertEqual(at(pp0, t), (at(d, t) >> 2) & 1, t)

    def test_level2_passes(self):
        result = replay(ARGS.stubs_vcd)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stderr.strip().splitlines()[-1])

    def test_two_levels_are_the_whole(self):
        whole = under(ARGS.whole, "TOP/punched_whole/dut")
        cut = under(ARGS.cut, "TOP/punched_cut_parent/dut")
        self.assertEqual(sorted(cut), sorted(whole))
        differ = [k for k in whole if whole[k] != cut[k]]
        self.assertEqual(differ, [])
        inside = [k for k in cut if k.startswith("u_core/")]
        toggles = sum(int(v[2]) for v in whole.values())
        print(
            "two levels vs whole: {} nets ({} in u_core, punched ports among "
            "them), {} toggles, 0 differ".format(len(whole), len(inside), toggles)
        )
        self.assertIn("u_core/net7_0", cut)
        self.assertGreater(sum(int(cut[k][2]) for k in inside), 0)

    def test_stale_punched_value_caught(self):
        # net7_0 (pp_1) one clock cycle late
        text = read(ARGS.stubs_vcd)
        head, body = text.split("$enddefinitions $end\n", 1)
        pp = ident(head, "pp_1")
        blocks = re.split(r"^#(\d+)\n", body, flags=re.M)
        times = [int(t) for t in blocks[1::2]]
        lines = [b.splitlines() for b in blocks[2::2]]
        moved = {}
        for t, ls in zip(times, lines):
            keep = [x for x in ls if x[1:] != pp]
            if t > 0:
                moved.setdefault(t + PERIOD, []).extend(x for x in ls if x[1:] == pp)
            ls[:] = keep if t > 0 else ls
        out = [head, "$enddefinitions $end\n"]
        for t, ls in zip(times, lines):
            out.append("#{}\n".format(t))
            out += [x + "\n" for x in ls + moved.get(t, [])]
        result = replay(write("".join(out)))
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertRegex(
            result.stderr, re.escape(LEVEL1) + r"\.q differs at cycle \d+ \(time"
        )

    def test_driven_output_differing_caught(self):
        # the captured q, a cell's output, inverted in bit 0 from the
        # start: level 2 fails at once, the first time
        bad = flip_bit(read(ARGS.stubs_vcd), LEVEL1 + ".q", 0)
        result = replay(write(bad))
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            LEVEL1 + ".q differs at cycle 0 (time 0, clock low)", result.stderr
        )

    def test_tied_output_not_compared(self):
        result = replay(ARGS.stubs_vcd)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stderr.splitlines()
        for line in (
            "replay: not compared, tie lo 0: " + LEVEL1 + ".mode[0]",
            "replay: not compared, tie hi 1: " + LEVEL1 + ".mode[1]",
        ):
            self.assertIn(line, lines)
            print(line)
        report = json.loads(read(ARGS.level2_report))
        self.assertEqual(
            sorted((n["bit"], n["reason"], n["value"]) for n in report["not_compared"]),
            [(0, "tie lo", 0), (1, "tie hi", 1)],
        )
        # level 1's stub drives mode as the gates do
        stub = json.loads(read(ARGS.stubs_json))["u_core"]
        self.assertEqual(
            sorted((f["bit"], f["value"]) for f in stub["outputs_fixed"]),
            [(0, 0), (1, 1)],
        )

    def test_undriven_stub_input_not_compared(self):
        tag = "TOP.Punched.rtl.u_core.tag"
        result = level1(ARGS.capture)
        self.assertEqual(result.returncode, 0, result.stderr)
        line = "replay: not compared, undriven: {}[1]".format(tag)
        self.assertIn(line, result.stderr.splitlines())
        print(line)
        report = json.loads(read(ARGS.level1_report))
        self.assertEqual(
            report["not_compared"],
            [{"signal": tag, "bit": 1, "reason": "undriven", "value": None}],
        )
        # the captured tag[1] inverted throughout: still not compared
        result = level1(write(flip_bit(read(ARGS.capture), tag, 1)))
        self.assertEqual(result.returncode, 0, result.stderr)
        # tag[0], r[0] through the pin, inverted: a stub input, so listed
        # every cycle, and fatal from the first one when strict
        bad = write(flip_bit(read(ARGS.capture), tag, 0))
        result = level1(bad)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(
            result.stderr,
            r"replay: stub input "
            + re.escape(tag)
            + r" differs in \d+ cycles, first at cycle 0: captured 00000001",
        )
        result = level1(bad, "--strict-stub-inputs")
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertIn(tag + " differs at cycle 0 (time 0, clock low)", result.stderr)

    def test_differing_outputs_counted(self):
        # the "matters" netlist again, its level 2 generated with
        # --count-outputs: acc's differences counted, the run complete
        acc = "TOP.punched_counted_parent.dut.u_core.acc"
        result = run(ARGS.counted_level2_bin, ARGS.counted_stubs_vcd)
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = re.search(
            r"^replay: output "
            + re.escape(acc)
            + r" differs in (\d+) cycles, first at cycle (\d+): captured (\w+), "
            r"netlist (\w+)$",
            result.stderr,
            re.M,
        )
        self.assertIsNotNone(listed, result.stderr)
        print(listed.group(0))
        cycles, first = int(listed.group(1)), int(listed.group(2))
        self.assertEqual(first, 1)  # where the uncounted replay fails
        total = (
            "replay: outputs differing from the RTL: 1 signals, {} cycles; first "
            "at cycle 1: {}".format(cycles, acc)
        )
        self.assertIn(total, result.stderr.splitlines())
        print(total)
        self.assertEqual(
            json.loads(read(ARGS.counted_outputs)),
            {
                "signals": 1,
                "cycles": cycles,
                "first_cycle": 1,
                "first_signal": acc,
                "top": [
                    {
                        "signal": acc,
                        "cycles": cycles,
                        "first_cycle": 1,
                        "captured": listed.group(3),
                        "netlist": listed.group(4),
                    }
                ],
            },
        )

    # the captured reset is asserted in cycles 2 to 4 and released at
    # time 5000: with --compare-from-reset, outputs from cycle 6 on
    FROM_RESET = (
        "replay: compared from cycle 6 (the cycle after the captured reset "
        "first falls, at time 5000)"
    )

    def test_rdy_differing_before_reset_not_compared(self):
        rdy = "TOP.punched_rdy_before_parent.dut.u_core.rdy"
        result = run(ARGS.rdy_before_bin, ARGS.rdy_before_stubs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.FROM_RESET, result.stderr.splitlines())
        print(self.FROM_RESET)
        # the same level 2 without the flag: rdy differs at the first edge
        result = run(ARGS.rdy_before_plain_bin, ARGS.rdy_before_stubs)
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertIn(rdy + " differs at cycle 0 (time 500, clock high)", result.stderr)

    def test_rdy_differing_during_reset_not_compared(self):
        result = run(ARGS.rdy_during_bin, ARGS.rdy_during_stubs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.FROM_RESET, result.stderr.splitlines())

    def test_rdy_differing_after_reset_caught(self):
        rdy = "TOP.punched_rdy_after_parent.dut.u_core.rdy"
        result = run(ARGS.rdy_after_strict_bin, ARGS.rdy_after_stubs)
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "replay: {} differs at cycle 6 (time 6000, clock low)".format(rdy),
            result.stderr,
        )
        # counted: from cycle 6 on, the run complete
        result = run(ARGS.rdy_after_counted_bin, ARGS.rdy_after_stubs)
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = re.search(
            r"^replay: output "
            + re.escape(rdy)
            + r" differs in (\d+) cycles, first at cycle 6:",
            result.stderr,
            re.M,
        )
        self.assertIsNotNone(listed, result.stderr)
        print(listed.group(0))
        self.assertEqual(
            json.loads(read(ARGS.rdy_after_from_reset)),
            {
                "reset": "TOP.punched_rdy_after_parent.dut.u_core.reset",
                "reset_falls_at": 5000,
                "compared_from_cycle": 6,
            },
        )
        outputs = json.loads(read(ARGS.rdy_after_outputs))
        self.assertEqual((outputs["first_signal"], outputs["first_cycle"]), (rdy, 6))

    def test_unit_output_differing_caught(self):
        # (A): the unit's own output dout, captured inverted in bit 0
        result = level1(write(flip_bit(read(ARGS.capture), "TOP.Punched.dout", 0)))
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "TOP.Punched.dout differs at cycle 0 (time 0, clock low)", result.stderr
        )

    def test_stub_inputs_all_match_here(self):
        result = level1(ARGS.capture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(NONE_DIFFER, result.stderr.splitlines())
        self.assertEqual(
            json.loads(read(ARGS.stub_inputs)), {"signals": 0, "cycles": 0, "top": []}
        )

    def test_stub_input_differing_on_a_dont_care(self):
        # data[0] is r[0] & v: wrong only while v is 0, ignored then
        result = run(ARGS.dontcare_level1_bin, ARGS.capture)
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = re.search(
            r"^replay: stub input "
            + re.escape(DATA)
            + r" differs in (\d+) cycles, first at cycle (\d+): captured (\w+), "
            r"netlist (\w+)$",
            result.stderr,
            re.M,
        )
        self.assertIsNotNone(listed, result.stderr)
        print(listed.group(0))
        cycles, first = int(listed.group(1)), int(listed.group(2))
        self.assertGreater(cycles, 10)
        total = (
            "replay: stub inputs differing from the RTL: 1 signals, {} cycles; not "
            "required to match, each piece's outputs are (level 2)".format(cycles)
        )
        self.assertIn(total, result.stderr.splitlines())
        print(total)
        self.assertEqual(
            json.loads(read(ARGS.dontcare_stub_inputs)),
            {
                "signals": 1,
                "cycles": cycles,
                "top": [
                    {
                        "signal": DATA,
                        "cycles": cycles,
                        "first_cycle": first,
                        "captured": listed.group(3),
                        "netlist": listed.group(4),
                    }
                ],
            },
        )
        # (B): the piece, driven with the netlist's data, still is its RTL
        result = run(ARGS.dontcare_level2_bin, ARGS.dontcare_stubs_vcd)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stderr.strip().splitlines()[-1])
        # strict: the same level 1 fails at the first differing cycle
        result = run(ARGS.dontcare_level1_bin, ARGS.capture, "--strict-stub-inputs")
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "replay: {} differs at cycle {} ".format(DATA, first), result.stderr
        )

    def test_stub_input_differing_where_it_matters(self):
        # data[0] is r[0] ^ v: wrong only while v is 1, taken then
        result = run(ARGS.matters_level1_bin, ARGS.capture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(
            result.stderr, r"replay: stub input " + re.escape(DATA) + r" differs in"
        )
        # (B) fails, at the piece's output acc
        result = run(ARGS.matters_level2_bin, ARGS.matters_stubs_vcd)
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertRegex(
            result.stderr,
            r"replay: TOP\.punched_matters_parent\.dut\.u_core\.acc differs at cycle \d+",
        )

    def test_swapped_aliases_caught(self):
        text = read(ARGS.stubs_vcd)
        head, body = text.split("$enddefinitions", 1)
        swapped = (
            head.replace(" pp_0 ", " pp_X ")
            .replace(" pp_1 ", " pp_0 ")
            .replace(" pp_X ", " pp_1 ")
        )
        self.assertNotEqual(swapped, head)
        result = replay(write(swapped + "$enddefinitions" + body))
        print(result.stderr.strip().splitlines()[-1])
        self.assertEqual(result.returncode, 1)
        self.assertRegex(
            result.stderr, re.escape(LEVEL1) + r"\.q differs at cycle \d+ \(time"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for k in (
        "whole",
        "cut",
        "capture",
        "stubs_vcd",
        "stubs_json",
        "level1_bin",
        "level1_report",
        "level2_bin",
        "level2_report",
        "dontcare_level1_bin",
        "dontcare_level2_bin",
        "dontcare_stubs_vcd",
        "dontcare_stub_inputs",
        "matters_level1_bin",
        "matters_level2_bin",
        "matters_stubs_vcd",
        "stub_inputs",
        "counted_level2_bin",
        "counted_stubs_vcd",
        "counted_outputs",
        "rdy_before_bin",
        "rdy_before_plain_bin",
        "rdy_before_stubs",
        "rdy_during_bin",
        "rdy_during_stubs",
        "rdy_after_strict_bin",
        "rdy_after_counted_bin",
        "rdy_after_stubs",
        "rdy_after_from_reset",
        "rdy_after_outputs",
    ):
        parser.add_argument("--" + k.replace("_", "-"), dest=k, required=True)
    ARGS = parser.parse_args()
    unittest.main(argv=sys.argv[:1])
