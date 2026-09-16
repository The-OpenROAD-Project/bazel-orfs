"""Tests for auto_period.py — the reg2reg period fixed point."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auto_period  # noqa: E402

PROBE = """\
stage 5_1_grt
clock clk
period_ps 1600.000000
wns_all_ps 5.807798686419119
reg2reg_paths_returned 8
reg2reg_slacks_ps 9.683144 12.782664 15.850210
reg2reg_worst_endpoint swerv.ifu.bp/bht_dataoutf.genblock.dff.dout[5]$_DFF_PN0_/D
wns_reg2reg_ps 9.683144
achieved_period_ps 1590.316856
achieved_mhz 628.8055089318628
"""

SDC = """\
# A starting period, not a result.
set clk_name clk
set clk_port_name clk
set clk_period 1600

set_max_delay 100
"""


class TestProbeReading(unittest.TestCase):
    def test_reads_the_three_numbers(self):
        period, wns, paths = auto_period.probe_reading(PROBE)
        self.assertEqual(period, 1600.0)
        self.assertAlmostEqual(wns, 9.683144)
        self.assertEqual(paths, 8)

    def test_no_paths_is_fatal_not_zero_slack(self):
        """A group that matched nothing reports the same 0 as no headroom."""
        text = PROBE.replace("reg2reg_paths_returned 8", "reg2reg_paths_returned 0")
        with self.assertRaises(auto_period.Fatal) as e:
            auto_period.probe_reading(text)
        self.assertIn("no reg2reg paths", str(e.exception))

    def test_missing_key_is_fatal(self):
        text = PROBE.replace("wns_reg2reg_ps 9.683144\n", "")
        with self.assertRaises(auto_period.Fatal):
            auto_period.probe_reading(text)


class TestConstraintsRewrite(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(auto_period.read_clk_period(SDC), 1600)
        out = auto_period.set_clk_period(SDC, 1590)
        self.assertEqual(auto_period.read_clk_period(out), 1590)

    def test_only_the_period_line_changes(self):
        out = auto_period.set_clk_period(SDC, 1590)
        self.assertEqual(
            [line for line in SDC.splitlines() if "clk_period" not in line],
            [line for line in out.splitlines() if "clk_period" not in line],
        )

    def test_missing_line_is_fatal(self):
        with self.assertRaises(auto_period.Fatal):
            auto_period.read_clk_period("set clk_name clk\n")

    def test_refuses_a_nonpositive_period(self):
        with self.assertRaises(auto_period.Fatal):
            auto_period.set_clk_period(SDC, 0)


class TestStep(unittest.TestCase):
    def test_rounds_away_from_the_designs_favour(self):
        """Ceil, so rounding can only ask for an easier period."""
        self.assertEqual(auto_period.next_candidate(1600, 9.683144), 1591)

    def test_negative_slack_overshoots_once_it_has_closed(self):
        self.assertEqual(
            auto_period.step(1590, -3.0, 2.0, True), ("overshot", 1590)
        )

    def test_negative_slack_relaxes_if_it_never_closed(self):
        """A start too tight to tune from is relaxed, not refused."""
        status, nxt = auto_period.step(1200, -73.988258, 2.0, False)
        self.assertEqual(status, "relax")
        self.assertGreater(nxt, 1200)

    def test_the_relax_overshoots_deliberately(self):
        """Because `period - WNS` is optimistic, measurably so."""
        _, nxt = auto_period.step(1200, -74.0, 2.0, False)
        self.assertGreater(nxt, 1274, "relaxing by exactly the deficit lands short")

    def test_small_slack_converges(self):
        self.assertEqual(
            auto_period.step(1590, 1.0, 2.0, True), ("converged", 1590)
        )

    def test_real_slack_continues(self):
        self.assertEqual(
            auto_period.step(1600, 9.683144, 2.0, False), ("continue", 1591)
        )


class TestDerive(unittest.TestCase):
    def _probe(self, table):
        def read(period_ps):
            if period_ps not in table:
                raise AssertionError("unexpected period %r" % period_ps)
            wns = table[period_ps]
            return (
                "period_ps %f\nwns_reg2reg_ps %f\nreg2reg_paths_returned 8\n"
                % (period_ps, wns)
            )

        return read

    def test_walks_down_to_the_tightest_closing_period(self):
        winner, status, history = self._derive({1600: 9.7, 1591: 4.2, 1587: 0.5})
        self.assertEqual(winner, 1587)
        self.assertEqual(status, "converged")
        self.assertEqual(len(history), 3)

    def _derive(self, table, **kw):
        return auto_period.derive(self._probe(table), 1600, **kw)

    def test_pins_the_last_period_that_closed_not_the_one_that_failed(self):
        winner, status, _ = self._derive({1600: 9.7, 1591: -2.0})
        self.assertEqual(winner, 1600)
        self.assertEqual(status, "overshot")

    def test_exhaustion_still_pins_a_closing_period(self):
        table = {1600: 30.0, 1570: 30.0, 1540: 30.0}
        winner, status, history = auto_period.derive(
            self._probe(table), 1600, max_iterations=3
        )
        self.assertEqual(status, "exhausted")
        self.assertEqual(winner, 1540)
        self.assertEqual(len(history), 3)

    def test_relaxes_up_to_a_closing_period_then_tightens(self):
        """ibex's case: the committed period is 74 ps too tight."""
        table = {1200: -73.988258, 1282: 6.0, 1276: 1.0}
        winner, status, history = auto_period.derive(self._probe(table), 1200)
        self.assertEqual(winner, 1276)
        self.assertEqual(status, "converged")
        self.assertFalse(history[0]["closed"])
        self.assertTrue(history[-1]["closed"])

    def test_a_design_that_never_closes_is_fatal(self):
        table = {1600: -5.0, 1606: -5.0, 1612: -5.0}
        with self.assertRaises(auto_period.Fatal) as e:
            auto_period.derive(self._probe(table), 1600, max_iterations=3)
        self.assertIn("relaxing is not finding", str(e.exception))

    def test_a_stale_artifact_is_fatal(self):
        """The failure mode that makes a loop converge on someone else's build."""

        def read(period_ps):
            return "period_ps 1600\nwns_reg2reg_ps 9.7\nreg2reg_paths_returned 8\n"

        with self.assertRaises(auto_period.Fatal) as e:
            auto_period.derive(read, 1591)
        self.assertIn("different build", str(e.exception))


if __name__ == "__main__":
    unittest.main()
