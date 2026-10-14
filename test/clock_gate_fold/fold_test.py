"""firtool folds Utility's clock gate when its enable is constant.

With patches/0010 (test/coremark_joule/xiangshan), Utility's ClockGate is
CIRCT's clock gate, and CLOCK_GATE_OPTS name the external module firtool
emits for the gates it keeps. Fold.scala has one gate whose enable is
true.B the way ExeUnit's CSR and fence gates are, and one with a live
enable: only the live one may be left, as an instance of ClockGate with
Utility's ports, and firtool must not define ClockGate itself (its body
is the checked-in ClockGate.sv).

Usage: fold_test.py <firtool output directory>
"""

import os
import re
import sys
import unittest

OUT = sys.argv[1]


def verilog():
    text = ""
    for root, _, files in os.walk(OUT):
        for name in sorted(files):
            if name.endswith((".sv", ".v")):
                with open(os.path.join(root, name)) as f:
                    text += f.read()
    return text


class FoldTest(unittest.TestCase):
    def setUp(self):
        self.text = verilog()
        self.assertIn("module Fold", self.text)

    def test_only_the_live_gate_is_left(self):
        instances = re.findall(r"^\s*ClockGate\s+\w+\s*\(", self.text, re.M)
        self.assertEqual(len(instances), 1, self.text)

    def test_the_gate_has_utility_ports(self):
        m = re.search(r"^\s*ClockGate\s+\w+\s*\((.*?)\);", self.text, re.M | re.S)
        ports = set(re.findall(r"\.(\w+)\s*\(", m.group(1)))
        self.assertEqual(ports, {"CK", "Q", "E", "TE"})

    def test_firtool_does_not_define_clock_gate(self):
        self.assertNotRegex(self.text, r"^\s*module\s+ClockGate\b")


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
