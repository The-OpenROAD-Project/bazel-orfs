"""SETUP_REPAIR_EFFORT reaches repair_timing as -effort.

The floorplan of lb_32x128_repair_effort sets SETUP_REPAIR_PHASES to
PARALLEL_EVAL and SETUP_REPAIR_EFFORT to low: its repair_timing command
line carries both, and repair_timing does not warn that the effort had
no effect (RSZ-3244, -effort without PARALLEL_EVAL).
"""

import os
import sys
import unittest

LOGS = sys.argv[1:]


def _log(name):
    found = [p for p in LOGS if os.path.basename(p) == name]
    if not found:
        raise AssertionError("no %s among %s" % (name, LOGS))
    with open(found[0]) as f:
        return f.read()


class SetupRepairEffortTest(unittest.TestCase):
    def test_effort_reaches_repair_timing(self):
        log = _log("2_1_floorplan.log")
        commands = [
            line for line in log.splitlines() if line.startswith("repair_timing ")
        ]
        self.assertEqual(len(commands), 1, commands)
        args = commands[0].split()
        self.assertIn("-effort", args)
        self.assertEqual(args[args.index("-effort") + 1], "low")
        self.assertEqual(args[args.index("-phases") + 1], "PARALLEL_EVAL")
        self.assertNotIn("RSZ-3244", log)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
