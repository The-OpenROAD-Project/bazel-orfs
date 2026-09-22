"""The checked-in plan of the miniature parent is what mini_gen.py and the
planner produce today; a change to either without regen.sh fails here."""

import os
import subprocess
import sys
import tempfile
import unittest


class PlanDriftTest(unittest.TestCase):
    def test_plan_dir_matches_the_generators(self):
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(os.path.dirname(here))
        out = tempfile.mkdtemp(prefix="planned_parent.")
        subprocess.check_call([sys.executable, os.path.join(here, "mini_gen.py"), "--out", out])
        # the planner's py_binary, in the runfiles next to this test
        planner = os.path.join(root, "tools", "macro_select", "plan_floorplan")
        subprocess.check_call(
            [planner, os.path.join(out, "plan.json"), "--out", os.path.join(out, "plan_out.json"), "--emit", out],
            cwd=root,
            stdout=subprocess.DEVNULL,
        )
        for f in ["BlockA_pins.tcl", "BlockB_pins.tcl", "BlockC_pins.tcl", "BlockD_pins.tcl", "place_macros.tcl", "netlists.txt", "plan.bzl"]:
            with open(os.path.join(out, f)) as a, open(os.path.join(here, "plan", f)) as b:
                self.assertEqual(a.read(), b.read(), "%s drifted: run test/planned_parent/regen.sh" % f)


if __name__ == "__main__":
    unittest.main()
