"""The macro_score audit math, on synthetic populations.

The campaign is hours of flow runtime and stays manual; CI holds still
the pieces a silent bug would poison: the candidate generator's
legality (a permutation must occupy exactly the winner's slots), the
penalty-table parser, the fixed-normalization score, and the audit
statistics with their tie handling.
"""

import random
import unittest

import macro_score as ms

BASE = [
    (f"m{i}", 10.0 + 90.0 * (i % 4), 10.0 + 80.0 * (i // 4), "R0")
    for i in range(16)
]
SIZES = {f"m{i}": {"w": 89.0, "h": 78.0} for i in range(16)}


class Generator(unittest.TestCase):
    def test_permutation_occupies_the_same_slots(self):
        rng = random.Random(1)
        for num_swaps in (2, 8, None):
            perm = ms.permute_assignment(BASE, rng, num_swaps=num_swaps)
            self.assertEqual(
                sorted((x, y) for _, x, y, _ in perm),
                sorted((x, y) for _, x, y, _ in BASE),
            )
            self.assertEqual(
                sorted(n for n, *_ in perm), sorted(n for n, *_ in BASE)
            )

    def test_swap_severity_is_graded(self):
        rng = random.Random(2)
        moved2 = sum(
            a != b
            for a, b in zip(ms.permute_assignment(BASE, rng, num_swaps=2), BASE)
        )
        # Two swaps move at most four macros, and at least two.
        self.assertGreaterEqual(moved2, 2)
        self.assertLessEqual(moved2, 4)

    def test_flip_changes_exactly_count_orientations(self):
        flipped = ms.flip_orientations(BASE, random.Random(3), 8)
        changed = sum(a[3] != b[3] for a, b in zip(flipped, BASE))
        self.assertEqual(changed, 8)
        # Locations never move.
        self.assertEqual(
            [(x, y) for _, x, y, _ in flipped], [(x, y) for _, x, y, _ in BASE]
        )

    def test_clumped_is_legal(self):
        packed = ms.clumped(BASE, SIZES)
        for _, x, y, _ in packed:
            self.assertGreaterEqual(x, 4.0)
            self.assertGreaterEqual(y, 4.0)
            self.assertLessEqual(x + 89.0, 396.0)
            self.assertLessEqual(y + 78.0, 396.0)
        # Non-overlapping: all lower-left corners distinct and spaced by
        # at least the macro size on one axis.
        corners = [(x, y) for _, x, y, _ in packed]
        self.assertEqual(len(set(corners)), len(corners))
        for i in range(len(corners)):
            for j in range(i + 1, len(corners)):
                dx = abs(corners[i][0] - corners[j][0])
                dy = abs(corners[i][1] - corners[j][1])
                self.assertTrue(dx >= 89.0 + 1.0 or dy >= 78.0 + 1.0)

    def test_clumped_that_cannot_fit_is_an_error(self):
        big = {f"m{i}": {"w": 200.0, "h": 200.0} for i in range(16)}
        with self.assertRaises(ValueError):
            ms.clumped(BASE, big)

    def test_place_file_round_trip(self, tmp="./tmp"):
        import os

        os.makedirs(tmp, exist_ok=True)
        path = os.path.join(tmp, "ms_test_place.tcl")
        ms.write_place_file(path, BASE)
        back = ms.parse_place_file(path)
        self.assertEqual(len(back), 16)
        self.assertEqual(back[0][0], "m0")
        self.assertAlmostEqual(back[5][1], BASE[5][1])
        os.remove(path)

    def test_nudged_core_is_site_exact(self):
        self.assertEqual(ms.nudged_core(-1), "4 4 395.946 396")
        self.assertEqual(ms.nudged_core(2), "4 4 396.108 396")


SYNTHETIC_LOG = """
noise
MS_TABLE_BEGIN w_base
[INFO] whatever
Cluster Placement Summary
  Penalty Type  |  Weight  |  Value  |  Norm. Factor  |  Cost
  Area          |  0.1     |  0.5    |  1.0           |  0.05
  Wire Length   |  100     |  2000   |  4000          |  50
  Boundary      |  50      |  10     |  20            |  25
  Total Cost                                     75.05
Macro Placement Summary
  Penalty Type  |  Weight  |  Value  |  Norm. Factor  |  Cost
  Area          |  0.1     |  0.5    |  1.0           |  0.05
  Wire Length   |  100     |  1000   |  4000          |  25
  Total Cost                                     25.05
MS_TABLE_END w_base
MS_TABLE_BEGIN d_bad
Macro Placement Summary
  Penalty Type  |  Weight  |  Value  |  Norm. Factor  |  Cost
  Wire Length   |  100     |  9000   |  4000          |  225
MS_TABLE_END d_bad
MS_COMPLIANCE d_bad 0.031
"""


class LogParser(unittest.TestCase):
    def test_tables_and_compliance(self):
        parsed = ms.parse_log_tables(SYNTHETIC_LOG)
        self.assertEqual(len(parsed["w_base"]["tables"]), 2)
        comps = ms.raw_components(parsed["w_base"]["tables"])
        self.assertAlmostEqual(comps["Wire Length"], 3000.0)
        self.assertAlmostEqual(comps["Area"], 1.0)
        self.assertAlmostEqual(comps["Boundary"], 10.0)
        self.assertAlmostEqual(parsed["d_bad"]["compliance_um"], 0.031)

    def test_fixed_normalization_score(self):
        parsed = ms.parse_log_tables(SYNTHETIC_LOG)
        base = ms.raw_components(parsed["w_base"]["tables"])
        s_base = ms.default_cost(base, base)
        s_bad = ms.default_cost(
            ms.raw_components(parsed["d_bad"]["tables"]), base
        )
        # Normalized against itself, each present term contributes its
        # weight; the degraded candidate's 3x wirelength dominates.
        self.assertGreater(s_bad, s_base)
        self.assertAlmostEqual(s_bad, 100.0 * 9000.0 / 3000.0)


class AuditMath(unittest.TestCase):
    def test_pick_accuracy_perfect_and_inverted(self):
        s = [1.0, 2.0, 3.0, 4.0]
        y = [10.0, 20.0, 30.0, 40.0]
        p, n = ms.kendall_pick(s, y, y_tie=0.0)
        self.assertEqual((p, n), (1.0, 6))
        p, _ = ms.kendall_pick(s, y[::-1], y_tie=0.0)
        self.assertEqual(p, 0.0)

    def test_ties_do_not_count(self):
        s = [1.0, 2.0, 3.0]
        y = [10.0, 10.4, 30.0]  # first pair inside the tie window
        p, n = ms.kendall_pick(s, y, y_tie=0.5)
        self.assertEqual(n, 2)
        self.assertEqual(p, 1.0)

    def test_all_ties_is_inconclusive(self):
        p, n = ms.kendall_pick([1.0, 2.0], [5.0, 5.1], y_tie=1.0)
        self.assertIsNone(p)
        self.assertEqual(n, 0)

    def test_auc(self):
        self.assertEqual(ms.auc([10, 11], [1, 2]), 1.0)
        self.assertEqual(ms.auc([1, 2], [10, 11]), 0.0)
        self.assertEqual(ms.auc([5], [5]), 0.5)

    def test_audit_end_to_end(self):
        rng = random.Random(4)
        candidates = {}
        # Winners: low score, low period; degraded: high score, high
        # period; the score is a noisy but real predictor.
        for i in range(8):
            y = 1000.0 + rng.gauss(0, 5)
            candidates[f"w_{i}"] = {
                "stratum": "W",
                "score": 10.0 + (y - 1000.0) / 5.0 + rng.gauss(0, 0.5),
                "kpis": {k: y for k in ms.KPIS},
            }
        for i in range(8):
            y = 1200.0 + rng.gauss(0, 20)
            candidates[f"d_{i}"] = {
                "stratum": "D_shuffle",
                "score": 60.0 + rng.gauss(0, 5),
                "kpis": {k: y for k in ms.KPIS},
            }
        doc = ms.audit(candidates, {k: 1000.0 for k in ms.KPIS}, {k: 1.0 for k in ms.KPIS})
        a = doc["achieved"]
        self.assertGreater(a["p_pick"], 0.8)
        self.assertGreater(a["auc_score_W_vs_D"], 0.9)
        self.assertGreater(a["auc_flow_W_vs_D"], 0.9)
        self.assertGreaterEqual(a["regret"], 0.0)
        self.assertIn("W", a["stratum_median_y"])
        self.assertLess(
            a["stratum_median_y"]["W"], a["stratum_median_y"]["D_shuffle"]
        )

    def test_blind_score_is_a_coin_flip(self):
        rng = random.Random(5)
        candidates = {
            f"c{i}": {
                "stratum": "W" if i % 2 else "D_x",
                "score": rng.random(),
                "kpis": {k: 1000.0 + i * 10.0 for k in ms.KPIS},
            }
            for i in range(20)
        }
        doc = ms.audit(candidates, {k: 1000.0 for k in ms.KPIS}, {k: 0.0 for k in ms.KPIS})
        p = doc["achieved"]["p_pick"]
        self.assertGreater(p, 0.25)
        self.assertLess(p, 0.75)


if __name__ == "__main__":
    unittest.main()
