#!/usr/bin/env python3
"""Unit tests for grafting units' gate-level SAIFs into the parent's."""

import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from saif_merge import Merge, main  # noqa: E402

HEAD = """(SAIFILE
(SAIFVERSION "2.0")
(DIRECTION "backward")
(DIVIDER / )
(TIMESCALE 1ps)
(DURATION {duration})
"""


def net(name, tc):
    return "   ({} (T0 50) (T1 50) (TZ 0) (TX 0) (TB 0) (TC {}))\n".format(name, tc)


def instance(name, nets, children=""):
    return (
        "  (INSTANCE {}\n   (NET\n".format(name)
        + "".join(net(n, tc) for n, tc in nets)
        + "   )\n"
        + children
        + "  )\n"
    )


def saif(body, duration=100, clock_tc=200):
    return (
        HEAD.format(duration=duration)
        + instance(
            "TOP", [("clock", clock_tc)], instance("dut", [("clock", clock_tc)], body)
        )
        + ")\n"
    )


# The parent's simulation: its own gates, the block as RTL, a register
# file inside it as RTL.
PARENT = saif(
    instance("_1_", [("Y", 7)])
    + instance(
        "u_blk",
        [("din", 3)],
        instance("rtl_reg", [("q", 1)]) + instance("u_rf", [("rd", 9)]),
    )
)
# The block's simulation: the block as gates, its register file as RTL,
# the parent as RTL.
BLOCK = saif(
    instance("parent_rtl_reg", [("q", 2)])
    + instance(
        "u_blk",
        [("din", 3)],
        instance("_5_", [("A", 4)]) + instance("u_rf", [("rd", 9)]),
    )
)
# The register file's simulation: only it as gates, at its RTL path.
FILE = saif(
    instance(
        "u_blk",
        [("din", 3)],
        instance("u_rf", [("rd", 9)], instance("_9_", [("A", 5)])),
    )
)


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def merge(self, parent, units, clock=("clock",)):
        out = io.StringIO()
        Merge(self.write("p.saif", parent), units, out, clock).run()
        return out.getvalue()

    def units(self, block=BLOCK, rf=FILE, rf_target="TOP/dut/u_blk/u_rf"):
        return [
            ("TOP/dut/u_blk", self.write("b.saif", block), "TOP/dut/u_blk"),
            (rf_target, self.write("f.saif", rf), "TOP/dut/u_blk/u_rf"),
        ]

    def test_units_replace_their_rtl_subtrees(self):
        merged = self.merge(PARENT, self.units())
        self.assertIn("(INSTANCE _1_", merged)  # the parent's gates
        self.assertIn("(INSTANCE _5_", merged)  # the block's gates
        self.assertIn("(INSTANCE _9_", merged)  # the file's gates, in the block
        self.assertNotIn("rtl_reg", merged)  # no RTL of a unit
        self.assertEqual(merged.count("(INSTANCE u_rf"), 1)
        self.assertEqual(merged.count("("), merged.count(")"))
        self.assertLess(merged.index("_5_"), merged.index("_9_"))

    def test_target_named_as_the_netlist_spells_it(self):
        # the block's netlist flattened `inner/u_rf` into one name
        block = BLOCK.replace("(INSTANCE u_rf", "(INSTANCE inner__SL__u_rf")
        merged = self.merge(
            PARENT, self.units(block=block, rf_target="TOP/dut/u_blk/inner__SL__u_rf")
        )
        self.assertIn("(INSTANCE inner__SL__u_rf", merged)
        self.assertIn("(INSTANCE _9_", merged)

    def test_header_mismatch_refused(self):
        with self.assertRaisesRegex(ValueError, "DURATION 99 against the parent's 100"):
            self.merge(PARENT, self.units(block=saif("", duration=99)))

    def test_clock_mismatch_refused(self):
        with self.assertRaisesRegex(ValueError, "the clock differs"):
            self.merge(PARENT, self.units(block=BLOCK.replace("(TC 200)", "(TC 198)")))

    def test_clock_at_a_units_root_compared(self):
        # the block's clock port, at its root, in its own gates: a second
        # clock pin a flow split off is the same clock
        units = self.units(
            block=saif(
                instance(
                    "u_blk",
                    [("clock", 200), ("clock_b", 198)],
                    instance("_5_", [("A", 4)]),
                )
            )
        )[:1]
        with self.assertRaisesRegex(ValueError, "clock_b"):
            self.merge(PARENT, units, clock=("clock", "clock_b"))

    def test_target_absent_refused(self):
        with self.assertRaisesRegex(
            ValueError, "no instance TOP/dut/u_blk/u_nope in the file"
        ):
            self.merge(PARENT, self.units(rf_target="TOP/dut/u_blk/u_nope"))

    def test_source_absent_refused(self):
        with self.assertRaisesRegex(ValueError, "no instance TOP/dut/u_blk/u_rf$"):
            self.merge(PARENT, self.units(rf=saif(instance("other", []))))

    def test_target_twice_refused(self):
        units = self.units()
        with self.assertRaisesRegex(ValueError, "given twice: TOP/dut/u_blk"):
            self.merge(PARENT, units + units[:1])

    def test_main(self):
        units = self.units()
        out = os.path.join(self.dir, "m.saif")
        args = [
            "--parent",
            self.write("p.saif", PARENT),
            "--out",
            out,
            "--clock",
            "clock",
        ]
        for t, p, s in units:
            args += ["--unit", "{}={}:{}".format(t, p, s)]
        self.assertEqual(main(args), 0)
        args[args.index("TOP/dut/u_blk={}:TOP/dut/u_blk".format(units[0][1]))] = (
            "TOP/dut/u_x={}:TOP/dut/u_blk".format(units[0][1])
        )
        self.assertEqual(main(args), 1)


if __name__ == "__main__":
    unittest.main()
