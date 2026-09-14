#!/usr/bin/env python3
"""Unit tests for the AUTO_MEMORIES guard.

The guard exists to catch a silent failure, so it is worth checking that
it actually catches it rather than trusting that it would.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_memories_applied import check  # noqa: E402

APPLIED = """
module cmj_picorv32 (clk, resetn);
  cpuregs \\cpu.cpuregs  (
    .clk(clk)
  );
endmodule
"""

FLOPS = """
module cmj_picorv32 (clk, resetn);
  DFFHQNx1_ASAP7_75t_R \\cpu.cpuregs[0][0]$_DFFE_PP_  (
    .CLK(clk)
  );
endmodule
"""


class CheckMemoriesAppliedTest(unittest.TestCase):
    def _netlist(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".v", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_instantiated_memory_passes(self):
        self.assertEqual(
            [], check(["cpuregs"], self._netlist(APPLIED), ["cpuregs"])
        )

    def test_memory_synthesised_as_flops_fails(self):
        """The real failure: blackboxed, generated, then not instantiated."""
        problems = check(["cpuregs"], self._netlist(FLOPS), ["cpuregs"])
        self.assertEqual(1, len(problems))
        self.assertIn("not instantiated", problems[0])

    def test_flop_names_do_not_count_as_instantiations(self):
        """A flop named after the memory must not satisfy the check.

        yosys names the flip-flops `\\cpu.cpuregs[0][0]$_DFFE_PP_`, so a
        substring search would find "cpuregs" in exactly the netlist the
        guard exists to reject.
        """
        self.assertIn(
            "cpuregs", open(self._netlist(FLOPS)).read()
        )
        self.assertNotEqual(
            [], check(["cpuregs"], self._netlist(FLOPS), ["cpuregs"])
        )

    def test_undetected_memory_fails_rather_than_passing_vacuously(self):
        """An empty blackboxes.txt must not be a silent pass."""
        problems = check([], self._netlist(FLOPS), ["cpuregs"])
        self.assertEqual(1, len(problems))
        self.assertIn("detection found nothing", problems[0])


if __name__ == "__main__":
    unittest.main()
