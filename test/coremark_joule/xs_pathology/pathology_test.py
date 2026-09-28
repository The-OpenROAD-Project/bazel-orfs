"""The pathology stand-in, from its records: B1 (the Frontend block's
settings) and S0 (the kept modules stated with SYNTH_HIERARCHICAL=0)."""

import json
import sys
import unittest

B1, S0 = (json.load(open(p)) for p in sys.argv[1:3])


class PathologyTest(unittest.TestCase):
    def test_kept_modules_are_the_stated_ones(self):
        for r in (B1, S0):
            self.assertEqual(sorted(r["kept"]), sorted(r["kept_expected"]))

    def test_stating_the_list_changes_nothing_else(self):
        self.assertEqual(S0["period_ps"], B1["period_ps"])

    def test_placement_legal(self):
        for r in (B1, S0):
            self.assertTrue(r["placement_ok"])


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
