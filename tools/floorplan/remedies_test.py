"""The remedies of two seeded faults, each run as a what-if on the toy's
frozen extracts: tens of seconds, apart from plan_test."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_test import toy  # noqa: E402


class Remedies(unittest.TestCase):
    def test_wall_remedies_are_what_ifs(self):
        _, _, v, _ = toy("wall", remedies=True)
        kinds = [r["kind"] for r in v["remedies"]]
        self.assertIn("change_side", kinds)
        best = v["remedies"][0]
        self.assertEqual(
            (best["kind"], best["effect"]["verdict"]), ("move_memory", "feasible")
        )
        self.assertEqual(best["for"]["side"], "W")

    def test_path_remedies(self):
        _, _, v, _ = toy("path", remedies=True)
        effects = {r["kind"]: r["effect"]["verdict"] for r in v["remedies"]}
        self.assertEqual(effects["register_bus"], "feasible")
        self.assertEqual(effects["move_slot"], "feasible")


if __name__ == "__main__":
    unittest.main()
