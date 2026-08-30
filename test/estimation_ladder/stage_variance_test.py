"""The math of stage_variance.py, on synthetic ensembles.

The walk itself is hours of flow runtime and stays manual; what CI can
and should hold still is the aggregation: the KPI candidate definitions,
the k-sizing arithmetic, the variance decomposition (and that it flags
an interaction instead of averaging it away), and the two guards -- a
null member that fails to reproduce the spine, and a clock nudge that
did not land, both of which must be errors rather than quiet zeros.
"""

import random
import unittest

import stage_variance as sv


def leaf(arm, tag, periods, clock_period=1000.0, area=100.0, tail_s=10.0):
    return {
        "arm": arm,
        "tag": str(tag),
        "time_unit": "ps",
        "clock_period": clock_period,
        "wns": clock_period - max(periods),
        "prefix_s": 0.0,
        "tail_s": tail_s,
        "sta_s": 0.0,
        "steps": {},
        "area": {
            "stdcell_um2": area,
            "macro_um2": 0.0,
            "num_stdcells": 10,
            "num_macros": 0,
        },
        "power_todo": area,
        "paths": [
            {"start": "a", "end": f"b{i}", "min_period": p, "macro_path": 0}
            for i, p in enumerate(periods)
        ],
    }


BASE_PERIODS = [900.0 + i for i in range(30)]  # 900..929, achieved 929


def ensemble(arm, tags, shift_per_tag, clock_period=1000.0):
    """One leaf per tag, all periods shifted by shift_per_tag[tag]."""
    return {
        (arm, str(t)): leaf(
            arm,
            t,
            [p + shift_per_tag[t] for p in BASE_PERIODS],
            clock_period=clock_period,
        )
        for t in tags
    }


class KpiCandidates(unittest.TestCase):
    def test_menu(self):
        k = sv.kpi_candidates(leaf("spine", "base", BASE_PERIODS))
        self.assertEqual(k["achieved"], 929.0)
        self.assertAlmostEqual(k["mean"], sum(BASE_PERIODS) / 30)
        self.assertAlmostEqual(k["top5_mean"], (929 + 928 + 927 + 926 + 925) / 5)
        # p90 of 0..29 evenly spaced: linear interpolation at index 26.1
        self.assertAlmostEqual(k["p90"], 900 + 26.1)
        self.assertEqual(k["area"], 100.0)
        self.assertEqual(k["power_todo"], 100.0)
        self.assertAlmostEqual(k["ppa_geomean"], (929.0 * 100.0 * 100.0) ** (1 / 3))
        # The trimmed mean drops the 3 worst and 3 best of 30.
        self.assertAlmostEqual(k["trimmed_mean_10"], sum(BASE_PERIODS[3:-3]) / 24)

    def test_empty_paths_is_an_error(self):
        with self.assertRaises(ValueError):
            sv.kpi_candidates(leaf("x", "y", []))


class Sizing(unittest.TestCase):
    def test_round_trip(self):
        # required_k inverts delta_min (up to the ceil).
        for k in (5, 10, 40):
            d = sv.delta_min(sigma=3.0, k=k)
            self.assertEqual(sv.required_k(sigma=3.0, delta=d), k)

    def test_more_members_resolve_less(self):
        self.assertLess(sv.delta_min(1.0, 40), sv.delta_min(1.0, 5))


class Decompose(unittest.TestCase):
    def draws(self, rng, sigma, n=40, mu=900.0):
        return [rng.gauss(mu, sigma) for _ in range(n)]

    def test_consistent_when_variances_add(self):
        rng = random.Random(1)
        per_arm = {
            "place": self.draws(rng, 4.0),
            "cts": self.draws(rng, 2.0),
            "grt": self.draws(rng, 1.0),
        }
        # sigma_all^2 = 16 + 4 + 1
        all_vals = self.draws(rng, 21.0**0.5)
        dec = sv.decompose(per_arm, all_vals)
        self.assertIn("consistent", dec["verdict"])
        lo, hi = dec["interaction_ci"]
        self.assertLess(lo, 0.0)
        self.assertGreater(hi, 0.0)

    def test_flags_interaction(self):
        rng = random.Random(2)
        per_arm = {
            "place": self.draws(rng, 1.0),
            "cts": self.draws(rng, 1.0),
            "grt": self.draws(rng, 1.0),
        }
        # The measured total is far wider than the sum: under-counted.
        all_vals = self.draws(rng, 15.0)
        dec = sv.decompose(per_arm, all_vals)
        self.assertIn("under-counted", dec["verdict"])
        self.assertGreater(dec["interaction_ci"][0], 0.0)


class Guards(unittest.TestCase):
    def spine_and_nulls(self, null_shift=0.0):
        spine = leaf("spine", "base", BASE_PERIODS)
        leaves = {("spine", "base"): spine}
        for arm in ("place", "cts", "grt"):
            leaves[(arm, "null")] = leaf(
                arm, "null", [p + null_shift for p in BASE_PERIODS]
            )
        return leaves, spine

    def test_nulls_pass_when_identical(self):
        leaves, spine = self.spine_and_nulls()
        self.assertEqual(sv.check_nulls(leaves, spine), [])

    def test_nulls_fail_on_drift(self):
        leaves, spine = self.spine_and_nulls(null_shift=1.0)
        failures = sv.check_nulls(leaves, spine)
        # A period shift moves achieved and mean but not area: two of the
        # three checked candidates fail, in each of the three arms.
        self.assertEqual(len(failures), 6)
        self.assertIn("not deterministic", failures[0])

    def test_missing_null_is_a_failure(self):
        leaves, spine = self.spine_and_nulls()
        del leaves[("grt", "null")]
        self.assertTrue(
            any("grt" in f and "missing" in f for f in sv.check_nulls(leaves, spine))
        )

    def test_nudge_landed(self):
        spine = leaf("spine", "base", BASE_PERIODS)
        leaves = {
            ("cts", "-2"): leaf("cts", "-2", BASE_PERIODS, clock_period=998.0),
            ("cts", "1"): leaf("cts", "1", BASE_PERIODS, clock_period=1001.0),
        }
        self.assertEqual(sv.check_nudges(leaves, spine, [-2, 1], all_k=0), [])

    def test_inert_nudge_is_an_error(self):
        spine = leaf("spine", "base", BASE_PERIODS)
        leaves = {
            ("cts", "3"): leaf("cts", "3", BASE_PERIODS, clock_period=1000.0),
        }
        failures = sv.check_nudges(leaves, spine, [3], all_k=0)
        self.assertEqual(len(failures), 1)
        self.assertIn("did not land", failures[0])


class Analyze(unittest.TestCase):
    def synthetic_run(self):
        rng = random.Random(3)
        cts_eps = [-2, -1, 1, 2]
        leaves = {("spine", "base"): leaf("spine", "base", BASE_PERIODS)}
        for arm, sigma in (("place", 4.0), ("grt", 1.0)):
            tags = list(range(1, 7))
            leaves.update(ensemble(arm, tags, {t: rng.gauss(0, sigma) for t in tags}))
            leaves[(arm, "null")] = leaf(arm, "null", BASE_PERIODS)
        eps_shift = {e: rng.gauss(0, 2.0) for e in cts_eps}
        leaves.update(
            {
                ("cts", str(e)): leaf(
                    "cts",
                    e,
                    [p + eps_shift[e] for p in BASE_PERIODS],
                    clock_period=1000.0 + e,
                )
                for e in cts_eps
            }
        )
        leaves[("cts", "null")] = leaf("cts", "null", BASE_PERIODS)
        all_k = 6
        for i in range(1, all_k + 1):
            leaves[("all", str(i))] = leaf(
                "all",
                i,
                [p + rng.gauss(0, 21.0**0.5) for p in BASE_PERIODS],
                clock_period=1000.0 + cts_eps[(i - 1) % len(cts_eps)],
            )
        return leaves, cts_eps, all_k

    def test_end_to_end(self):
        leaves, cts_eps, all_k = self.synthetic_run()
        result = sv.analyze(
            leaves, {"spine_steps": {"cts.tcl": 5.0}, "prefix_s": 5.0}, cts_eps, all_k
        )
        self.assertEqual(result["guards"]["null_failures"], [])
        self.assertEqual(result["guards"]["nudge_failures"], [])
        self.assertIn("achieved", result["decomposition"])
        self.assertEqual(result["arms"]["place"]["stats"]["achieved"]["n"], 6)
        # Every pareto row prices k members at k tails.
        row = result["pareto"][0]
        self.assertAlmostEqual(row["cpu_s"], 10.0 * row["k"])
        # The raw material survives, so future candidates need no re-run.
        raw = result["arms"]["grt"]["raw"]["1"]
        self.assertEqual(len(raw["min_periods"]), len(BASE_PERIODS))


class Percentile(unittest.TestCase):
    def test_bounds_and_interpolation(self):
        self.assertEqual(sv.percentile([5.0], 0.99), 5.0)
        self.assertEqual(sv.percentile([1.0, 2.0], 0.0), 1.0)
        self.assertEqual(sv.percentile([1.0, 2.0], 1.0), 2.0)
        self.assertAlmostEqual(sv.percentile([1.0, 2.0], 0.5), 1.5)
        with self.assertRaises(ValueError):
            sv.percentile([], 0.5)


if __name__ == "__main__":
    unittest.main()
