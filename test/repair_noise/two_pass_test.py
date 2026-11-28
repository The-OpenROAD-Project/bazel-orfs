"""The two-pass study's parsers and decision rule, on small fixtures."""

import math
import os
import tempfile
import unittest

import two_pass as tp


class PeriodTest(unittest.TestCase):
    def test_design_clock_not_virtual(self):
        m = {
            "globalroute__timing__fmax": 3e9,
            "globalroute__timing__fmax__clock:core_clock": 1e9,
            "globalroute__timing__fmax__clock:vclk_core_clock": 3e9,
        }
        self.assertAlmostEqual(tp.design_period_ps(m), 1000.0)

    def test_slowest_real_clock(self):
        m = {
            "globalroute__timing__fmax__clock:a": 1e9,
            "globalroute__timing__fmax__clock:b": 0.5e9,
        }
        self.assertAlmostEqual(tp.design_period_ps(m), 2000.0)

    def test_none_without_clock(self):
        self.assertIsNone(tp.design_period_ps({"globalroute__timing__fmax": 1e9}))


class TsvTest(unittest.TestCase):
    def test_comments_dropped(self):
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as fh:
            fh.write("# pin\trise_max (ps)\n#sdc set_clock_latency 1 x\n")
            fh.write("a/CK\t1.5\t1.0\t1.5\t1.0\n")
        try:
            self.assertEqual(
                tp.read_tsv(fh.name), [["a/CK", "1.5", "1.0", "1.5", "1.0"]]
            )
        finally:
            os.unlink(fh.name)


class GapTest(unittest.TestCase):
    def test_identical_readings(self):
        rows = [["p%d" % i, str(i), str(i), str(i)] for i in range(20)]
        g = tp.gap_metrics(rows, share=0.1)
        self.assertEqual(g["pins"], 20)
        self.assertEqual(g["overlap_total"], 1.0)
        self.assertAlmostEqual(g["rho_total"], 1.0)

    def test_reversed_wire(self):
        # placement ranks the nets backwards: no overlap, rho -1
        rows = [["p%d" % i, str(i), str(i), str(-i)] for i in range(20)]
        g = tp.gap_metrics(rows, share=0.1)
        self.assertEqual(g["overlap_clock"], 1.0)
        self.assertEqual(g["overlap_wire"], 0.0)
        self.assertAlmostEqual(g["rho_wire"], -1.0)

    def test_unconstrained_dropped(self):
        rows = [["a", "INF", "1", "1"], ["b", "1", "1", "1"], ["c", "x", "1", "1"]]
        self.assertEqual(tp.gap_metrics(rows)["pins"], 1)


class LatencyTest(unittest.TestCase):
    def test_stats(self):
        s = tp.latency_stats([["a", "10"], ["b", "20"], ["c", "x"]])
        self.assertEqual(s["sinks"], 2)
        self.assertEqual((s["min"], s["max"], s["mean"]), (10.0, 20.0, 15.0))


class LogTest(unittest.TestCase):
    def test_took_and_elapsed(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
            fh.write("Took 7 seconds: repair_timing\nTook 3 seconds: other\n")
            fh.write("Took 5 seconds: repair_timing\n")
            fh.write("Elapsed time: 0:01:02.50[h:]min:sec. CPU time: x\n")
        try:
            self.assertEqual(tp.took(fh.name, "repair_timing"), 12)
            self.assertAlmostEqual(tp.elapsed_s(fh.name), 62.5)
        finally:
            os.unlink(fh.name)


def _results(deltas, sigma=10.0, seed=None):
    out = []
    for i, d in enumerate(deltas):
        arms = {"base": {"period_ps": 1000.0}, "tp_clk": {"period_ps": 1000.0 + d}}
        if seed is not None:
            arms["seed2"] = {"period_ps": 1000.0 + seed[i]}
        out.append({"key": "d%d" % i, "sigma_ps": sigma, "arms": arms})
    return out


class VerdictTest(unittest.TestCase):
    def test_consistent_gain_is_above_floor(self):
        v = tp.verdicts(_results([-20.0] * 9))
        x = v["tp_clk"]
        self.assertAlmostEqual(x["Z"], -20 / (math.sqrt(2) * 10) * 3)
        self.assertEqual(tp.verdict_word(x), "better, above the floor")

    def test_mixed_is_within_floor(self):
        v = tp.verdicts(_results([-10.0, 10.0] * 4))
        self.assertEqual(tp.verdict_word(v["tp_clk"]), "within the floor")

    def test_seed_scales_sigma_up_only(self):
        big = tp.verdicts(_results([0.0] * 4, seed=[40.0, -40.0, 40.0, -40.0]))
        self.assertAlmostEqual(big["sigma_scale"], 40 / (math.sqrt(2) * 10))
        small = tp.verdicts(_results([0.0] * 4, seed=[0.0] * 4))
        self.assertEqual(small["sigma_scale"], 1.0)

    def test_missing_arm(self):
        self.assertEqual(
            tp.verdict_word(tp.verdicts(_results([1.0]))["tp_vcts"]), "not yet measured"
        )

    def test_render_names_failure(self):
        r = _results([-5.0])
        r[0]["key"] = "asap7/gcd"  # the report lists the panel's designs
        del r[0]["arms"]["tp_clk"]
        r[0]["failed"] = {"tp_clk": "[ERROR RSZ-0060] Max buffer count reached."}
        text = tp.render(r)
        self.assertIn("| failed |", text)
        self.assertIn("RSZ-0060", text)

    def test_render_says_not_yet_measured(self):
        text = tp.render(_results([-5.0]))
        self.assertIn("not yet measured", text)
        with self.assertRaises(SystemExit):
            tp.render([])


if __name__ == "__main__":
    unittest.main()
