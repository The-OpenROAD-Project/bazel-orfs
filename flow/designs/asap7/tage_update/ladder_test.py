"""ladder.bzl's LADDER says what config.mk's FLOW_VARIANT blocks say."""

import pathlib
import re
import sys
import unittest


class LadderTest(unittest.TestCase):
    def setUp(self):
        config, bzl = sys.argv[1], sys.argv[2]
        self.mk = pathlib.Path(config).read_text()
        self.bzl = pathlib.Path(bzl).read_text()
        self.ladder = dict(re.findall(r'"(\w+)":\s*"([^"]+)"', self.bzl))

    def test_same_ladder(self):
        blocks = dict(
            re.findall(
                r"ifeq \(\$\(FLOW_VARIANT\),(\w+)\)\s*\nexport VERILOG_TOP_PARAMS\s*=\s*(.+)",
                self.mk.replace("else ifeq", "ifeq"),
            )
        )
        self.assertEqual(
            {k: v.strip() for k, v in blocks.items()},
            self.ladder,
            "config.mk vs ladder.bzl",
        )

    def test_base_is_a_rung(self):
        base = re.search(r'^BASE = "(\w+)"', self.bzl, re.M).group(1)
        default = re.search(
            r"^else\s*\nexport VERILOG_TOP_PARAMS\s*=\s*(.+)", self.mk, re.M
        ).group(1)
        self.assertEqual(default.strip(), self.ladder[base], "base vs BASE")
        self.assertIn("base, ORFS's default\n# variant, is " + base, self.mk)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
