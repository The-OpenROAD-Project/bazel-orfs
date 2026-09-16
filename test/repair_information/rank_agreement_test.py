"""Tests for the rank-agreement statistics.

The whole Part A verdict is read off these three numbers, so they are
tested against cases whose answer is known by construction rather than
against a recorded run: a perfect ranking, a reversed one, a constant
column, and a shuffle confined to the bulk that leaves the critical top
untouched -- which is the case the study most needs to be able to tell
apart from a real disagreement.
"""

import unittest

import rank_agreement as ra


class RanksTest(unittest.TestCase):
    def test_ascending(self):
        self.assertEqual(ra.ranks([10.0, 20.0, 30.0]), [1.0, 2.0, 3.0])

    def test_ties_are_averaged(self):
        # Without averaging, the emission order of an equal-slack plateau
        # would decide the agreement number.
        self.assertEqual(ra.ranks([5.0, 5.0, 9.0]), [1.5, 1.5, 3.0])

    def test_unsorted_input(self):
        self.assertEqual(ra.ranks([3.0, 1.0, 2.0]), [3.0, 1.0, 2.0])


class SpearmanTest(unittest.TestCase):
    def slacks(self, values):
        return {f"ep{i}": v for i, v in enumerate(values)}

    def test_identical_is_one(self):
        a = self.slacks([1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(ra.spearman(a, a, sorted(a)), 1.0)

    def test_reversed_is_minus_one(self):
        a = self.slacks([1.0, 2.0, 3.0, 4.0])
        b = self.slacks([4.0, 3.0, 2.0, 1.0])
        self.assertAlmostEqual(ra.spearman(a, b, sorted(a)), -1.0)

    def test_offset_does_not_move_rank(self):
        # A model wrong by a constant ranks perfectly, and for driving a
        # repair that is all that is asked of it.
        a = self.slacks([1.0, 2.0, 3.0])
        b = self.slacks([101.0, 102.0, 103.0])
        self.assertAlmostEqual(ra.spearman(a, b, sorted(a)), 1.0)

    def test_constant_column_is_undefined_not_zero(self):
        a = self.slacks([1.0, 2.0, 3.0])
        b = self.slacks([7.0, 7.0, 7.0])
        self.assertIsNone(ra.spearman(a, b, sorted(a)))


class CompareTest(unittest.TestCase):
    def slacks(self, values):
        return {f"ep{i:03d}": v for i, v in enumerate(values)}

    def test_top_k_survives_a_shuffled_bulk(self):
        # The four worst endpoints agree; everything above them is
        # permuted. Spearman drops, top-k overlap stays perfect, and the
        # study cares about the second one.
        ref = self.slacks([-4.0, -3.0, -2.0, -1.0] + list(range(20)))
        cand = self.slacks([-4.0, -3.0, -2.0, -1.0] + list(reversed(range(20))))
        out = ra.compare(ref, cand, k_fractions=(0.10,))
        row = out["top_k"][0]
        self.assertEqual(row["k"], 2)
        self.assertEqual(row["overlap"], 2)
        self.assertEqual(row["missed_count"], 0)
        self.assertLess(out["spearman"], 1.0)

    def test_missed_endpoints_are_named(self):
        ref = self.slacks([-9.0, -8.0, 1.0, 2.0])
        # The candidate thinks the two worst are fine and the two fine
        # ones are worst: a repair driven by it never looks at ep000.
        cand = self.slacks([3.0, 4.0, -9.0, -8.0])
        out = ra.compare(ref, cand, k_fractions=(0.5,))
        row = out["top_k"][0]
        self.assertEqual(row["k"], 2)
        self.assertEqual(row["overlap"], 0)
        self.assertEqual(row["missed"], ["ep000", "ep001"])

    def test_common_endpoints_are_the_intersection(self):
        ref = self.slacks([1.0, 2.0, 3.0])
        cand = dict(self.slacks([1.0, 2.0, 3.0]))
        cand["buffer_added_later"] = 0.5
        del cand["ep002"]
        out = ra.compare(ref, cand, k_fractions=(0.5,))
        self.assertEqual(out["endpoints_common"], 2)
        self.assertEqual(out["endpoints_reference"], 3)
        self.assertEqual(out["endpoints_candidate"], 3)

    def test_disjoint_endpoints_fail_loudly(self):
        with self.assertRaises(SystemExit):
            ra.compare({"a": 1.0}, {"b": 1.0})

    def test_slack_error_is_a_diagnostic_not_the_verdict(self):
        ref = self.slacks([0.0, 1.0, 2.0])
        cand = self.slacks([10.0, 11.0, 12.0])
        out = ra.compare(ref, cand, k_fractions=(0.5,))
        self.assertAlmostEqual(out["slack_error"]["mean"], 10.0)
        self.assertAlmostEqual(out["slack_error"]["two_sigma"], 0.0)
        self.assertAlmostEqual(out["spearman"], 1.0)


if __name__ == "__main__":
    unittest.main()
