"""Tests for the two floors.

The cases that matter are the ones where the two floors disagree, since
that is the whole reason the module reports both: a difference can be
resolvable and invisible to CI, or inside the seed noise and large
enough that a rule would have fired.
"""

import json
import tempfile
import unittest
from pathlib import Path

import noise_floor as nf


class FloorsTest(unittest.TestCase):
    def test_tolerance_bar_is_a_fraction_of_the_clock(self):
        self.assertAlmostEqual(nf.tolerance_bar_ps(1000.0), 50.0)
        self.assertAlmostEqual(nf.tolerance_bar_ps(330.0), 16.5)

    def test_single_sample_has_zero_spread(self):
        self.assertEqual(nf.two_sigma([300.0]), 0.0)
        self.assertEqual(nf.two_sigma([]), 0.0)

    def test_two_sigma_of_a_known_sample(self):
        # Sample stdev of [1,2,3] is 1.0.
        self.assertAlmostEqual(nf.two_sigma([1.0, 2.0, 3.0]), 2.0)

    def test_resolution_improves_with_repeats(self):
        self.assertGreater(nf.resolvable(1, 10.0), nf.resolvable(12, 10.0))
        self.assertAlmostEqual(nf.resolvable(2, 10.0), 10.0)

    def test_no_runs_is_an_error_not_infinity(self):
        with self.assertRaises(ValueError):
            nf.resolvable(0, 10.0)


class VerdictTest(unittest.TestCase):
    def floor(self, clock, samples):
        return nf.floors("d", clock, samples)

    def test_without_repeats_nothing_may_be_claimed(self):
        floor = self.floor(1000.0, [])
        self.assertIn("not measured", nf.verdict(999.0, floor))

    def test_inside_the_resolution_is_never_no_effect(self):
        # 2 sigma = 20, k = 3 -> resolves ~16.3 ps.
        floor = self.floor(1000.0, [290.0, 300.0, 310.0])
        self.assertEqual(nf.verdict(5.0, floor), "did not resolve")

    def test_resolved_but_below_what_ci_notices(self):
        # Tight ensemble, loose clock: 2 sigma = 0.2 ps resolves 0.16 ps,
        # while the CI bar is 50 ps. A real 10 ps effect is invisible to
        # every rule in rules-base.json and still a result.
        floor = self.floor(1000.0, [300.0, 300.1, 300.2])
        self.assertEqual(
            nf.verdict(10.0, floor), "resolved, below the CI tolerance bar"
        )

    def test_resolved_and_above_the_bar(self):
        floor = self.floor(300.0, [300.0, 300.1, 300.2])
        self.assertEqual(
            nf.verdict(40.0, floor), "resolved, above the CI tolerance bar"
        )

    def test_sign_does_not_change_the_verdict(self):
        floor = self.floor(1000.0, [290.0, 300.0, 310.0])
        self.assertEqual(nf.verdict(-5.0, floor), nf.verdict(5.0, floor))


class RuleFileTest(unittest.TestCase):
    def write(self, payload):
        path = Path(tempfile.mkdtemp()) / "rules-base.json"
        path.write_text(json.dumps(payload))
        return path

    def test_reads_the_padded_threshold(self):
        path = self.write({"finish__timing__setup__ws": {"value": -24.2}})
        self.assertAlmostEqual(nf.read_rule(path, "finish__timing__setup__ws"), -24.2)

    def test_absent_rule_is_none_not_zero(self):
        path = self.write({"detailedroute__route__drc_errors": {"value": 0}})
        self.assertIsNone(nf.read_rule(path, "finish__timing__setup__ws"))


if __name__ == "__main__":
    unittest.main()
