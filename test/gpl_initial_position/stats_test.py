"""Unit tests for the resolution and concordance arithmetic."""

import math
import unittest

import stats


class SpreadTest(unittest.TestCase):
    def test_mean_of_nothing_raises(self):
        with self.assertRaises(ValueError):
            stats.mean([])

    def test_single_sample_has_no_spread(self):
        self.assertEqual(stats.stdev([1.0]), 0.0)
        self.assertEqual(stats.spread([4.0])["two_sigma"], 0.0)

    def test_two_sigma_is_twice_the_sample_deviation(self):
        values = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(stats.spread(values)["sd"], 1.2909944, places=6)
        self.assertAlmostEqual(
            stats.spread(values)["two_sigma"], 2 * 1.2909944, places=6
        )


class ResolutionTest(unittest.TestCase):
    def test_one_sample_arm_cannot_resolve_anything(self):
        self.assertEqual(stats.resolution([1.0, 2.0], [5.0]), math.inf)
        self.assertEqual(stats.resolution([1.0], [5.0, 6.0]), math.inf)

    def test_matches_the_closed_form_for_equal_arms(self):
        # Equal sd and equal n reduce 2*sqrt(s^2/k + s^2/k) to 2*s*sqrt(2/k),
        # which is the form the plan and the PR body quote.
        arm_a = [10.0, 12.0, 14.0, 16.0]
        arm_b = [20.0, 22.0, 24.0, 26.0]
        sd = stats.stdev(arm_a)
        self.assertAlmostEqual(stats.stdev(arm_b), sd, places=12)
        self.assertAlmostEqual(
            stats.resolution(arm_a, arm_b), 2 * sd * math.sqrt(2 / 4), places=12
        )

    def test_resolution_is_the_closed_form_at_every_k(self):
        for k in (2, 4, 8, 16, 32):
            arm = [float(i) for i in range(k)]
            sd = stats.stdev(arm)
            self.assertAlmostEqual(
                stats.resolution(arm, arm), 2 * sd * math.sqrt(2 / k), places=12
            )

    def test_quadrupling_k_at_fixed_spread_halves_the_resolution(self):
        # The spread has to be held equal for the claim to mean
        # anything: simply replicating samples lowers the n-1 deviation
        # as well as raising n, and the two effects do not cancel.
        small = [float(i) for i in range(4)]
        large = [float(i) for i in range(16)]
        factor = stats.stdev(small) / stats.stdev(large)
        large = [value * factor for value in large]
        self.assertAlmostEqual(stats.stdev(large), stats.stdev(small), places=12)
        self.assertAlmostEqual(
            stats.resolution(large, large) / stats.resolution(small, small),
            0.5,
            places=12,
        )


class CompareTest(unittest.TestCase):
    def test_a_difference_inside_the_band_does_not_resolve(self):
        row = stats.compare([100.0, 101.0, 99.0, 100.0], [100.5, 101.5, 99.5, 100.5])
        self.assertEqual(row["verdict"], "did not resolve")
        self.assertEqual(row["direction"], 0)

    def test_a_difference_outside_the_band_resolves_with_a_sign(self):
        row = stats.compare([100.0, 101.0, 99.0, 100.0], [200.0, 201.0, 199.0, 200.0])
        self.assertEqual(row["verdict"], "resolved")
        self.assertEqual(row["direction"], 1)
        self.assertAlmostEqual(row["delta"], 100.0, places=6)

    def test_an_unresolved_comparison_contributes_no_direction(self):
        # The sign of a difference that did not resolve is not evidence,
        # and must never reach the concordance count.
        row = stats.compare([1.0, 2.0, 3.0], [1.1, 2.1, 3.1])
        self.assertEqual(row["direction"], 0)


class BinomialTest(unittest.TestCase):
    def test_degenerate_thresholds(self):
        self.assertEqual(stats.binomial_tail(5, 0, 0.3), 1.0)
        self.assertEqual(stats.binomial_tail(5, 6, 0.3), 0.0)

    def test_known_value(self):
        # P(>=1 head in 2 fair flips) = 3/4.
        self.assertAlmostEqual(stats.binomial_tail(2, 1, 0.5), 0.75, places=12)


class FamilyErrorTest(unittest.TestCase):
    def test_the_sizing_in_the_plan_holds(self):
        # 12 designs, 8 arms, 4 of 12 required: the plan claims ~0.4%.
        rate = stats.family_error(designs=12, required=4, arms=8)
        self.assertLess(rate, 0.01)
        self.assertAlmostEqual(rate, 0.004, delta=0.002)

    def test_three_of_twelve_is_not_enough(self):
        # Which is why the rule is 4 and not 3: more designs means more
        # chances, so the threshold has to rise with D.
        self.assertGreater(stats.family_error(designs=12, required=3, arms=8), 0.01)

    def test_required_concordance_picks_that_threshold(self):
        self.assertEqual(stats.required_concordance(designs=12, arms=8), 4)
        self.assertEqual(stats.required_concordance(designs=6, arms=8), 3)

    def test_unanimity_is_returned_when_the_target_is_unreachable(self):
        self.assertEqual(
            stats.required_concordance(designs=2, arms=8, target=1e-9), 2
        )


class VerdictTest(unittest.TestCase):
    @staticmethod
    def _rows(directions):
        return [{"direction": d} for d in directions]

    def test_nothing_resolving_is_not_a_finding(self):
        out = stats.verdict(self._rows([0] * 12), arms=8)
        self.assertEqual(out["label"], "did not resolve")

    def test_four_of_twelve_in_one_direction_is_a_finding(self):
        out = stats.verdict(self._rows([-1] * 4 + [0] * 8), arms=8)
        self.assertEqual(out["label"], "better")
        self.assertEqual(out["required"], 4)
        self.assertEqual(out["agree"], 4)

    def test_three_of_twelve_is_not(self):
        out = stats.verdict(self._rows([-1] * 3 + [0] * 9), arms=8)
        self.assertEqual(out["label"], "did not resolve")

    def test_designs_disagreeing_is_its_own_verdict(self):
        # Not "no effect": a real but design-dependent effect looks
        # exactly like this, and collapsing it into silence would hide
        # the most interesting outcome the campaign can produce.
        out = stats.verdict(self._rows([1, 1, 1, -1, -1, -1] + [0] * 6), arms=8)
        self.assertEqual(out["label"], "inconsistent")

    def test_too_few_designs_cannot_produce_a_finding(self):
        # One design and nine arms: even a unanimous, resolved direction
        # is well inside what chance produces, so the label must say so
        # rather than print "better" over a 45% family-wise error.
        out = stats.verdict(self._rows([-1]), arms=9)
        self.assertEqual(out["label"], "underpowered")
        self.assertTrue(out["underpowered"])
        self.assertGreater(out["family_error"], 0.01)

    def test_a_powered_campaign_is_not_flagged(self):
        out = stats.verdict(self._rows([-1] * 4 + [0] * 8), arms=8)
        self.assertFalse(out["underpowered"])
        self.assertEqual(out["label"], "better")

    def test_both_directions_clearing_the_bar_is_inconsistent(self):
        # Six designs better and four worse is not a "better" arm. It is
        # a real effect whose sign depends on the design, and reporting
        # the majority direction would claim a universal law.
        out = stats.verdict(self._rows([-1] * 6 + [1] * 4 + [0] * 2), arms=8)
        self.assertEqual(out["label"], "inconsistent")

    def test_a_minority_below_the_bar_does_not_block_a_finding(self):
        # Three opposing designs is below the evidence threshold, so the
        # arm still reads as better -- but the count is surfaced.
        out = stats.verdict(self._rows([-1] * 6 + [1] * 3 + [0] * 3), arms=8)
        self.assertEqual(out["label"], "better")
        self.assertEqual(out["up"], 3)
        self.assertEqual(out["down"], 6)

    def test_sign_convention_is_lower_is_better(self):
        out = stats.verdict(self._rows([1] * 6 + [0] * 6), arms=8)
        self.assertEqual(out["label"], "worse")


if __name__ == "__main__":
    unittest.main()
