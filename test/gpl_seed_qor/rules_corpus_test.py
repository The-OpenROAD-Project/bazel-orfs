"""The inversion, driven forwards by genRuleFile's own formula.

The risk this guards against is not a typo in the algebra -- it is
genRuleFile.py changing its padding policy under us, at which point the
recovered numbers stay plausible and become wrong. So the test carries
its own forward implementation, written from the upstream source, and
requires the inverse to undo it exactly. A policy change upstream makes
`pad()` disagree with reality, and the corpus snapshot's ORFS commit is
what says which policy a stored row was read under.
"""

import unittest

import rules_corpus


def pad(measured, period, padding_pct):
    """genRuleFile.py's period_padding mode, written out longhand.

    Args:
        measured: the metric as the flow measured it.
        period: the first clock's period.
        padding_pct: 5 for a ws metric, 20 for a tns metric.

    Returns:
        The rule value ORFS would write, before its rounding.
    """
    negative_slack = min(measured, 0)
    return negative_slack - max(
        negative_slack * padding_pct / 100.0, period * padding_pct / 100.0
    )


def round_3g(value):
    """The three-significant-figure rounding ORFS applies to the bound."""
    return float("%.3g" % value)


class PadRoundTrip(unittest.TestCase):
    def test_negative_metric_comes_back(self):
        period = 380.0
        for measured in (-8.8, -0.5, -250.0):
            for padding in (5, 20):
                rule = pad(measured, period, padding)
                recovered, censored = rules_corpus.recover_measurement(
                    rule, padding, period
                )
                self.assertFalse(censored)
                self.assertAlmostEqual(recovered, measured, places=9)

    def test_a_violation_below_the_rounding_resolution_reads_as_censored(self):
        # -19.0 resolves to 0.05, so a 0.01 ps violation is not in the
        # file to be recovered. Reported as censored rather than as a
        # slack of -0.01 that the rounding could equally have produced
        # from zero.
        period = 380.0
        rule = round_3g(pad(-0.01, period, 5))
        value, censored = rules_corpus.recover_measurement(rule, 5, period)
        self.assertTrue(censored)
        self.assertIsNone(value)
        self.assertAlmostEqual(rules_corpus.rule_resolution(-19.0), 0.05)
        self.assertAlmostEqual(rules_corpus.rule_resolution(-1737.0), 5.0)

    def test_non_negative_metric_reads_as_censored(self):
        period = 380.0
        for measured in (0.0, 12.5, 900.0):
            rule = pad(measured, period, 5)
            value, censored = rules_corpus.recover_measurement(rule, 5, period)
            self.assertTrue(censored)
            self.assertIsNone(value)

    def test_rounding_keeps_the_recovery_within_a_tenth_of_a_percent(self):
        period = 310.0
        measured = -47.3
        rule = round_3g(pad(measured, period, 5))
        recovered, _ = rules_corpus.recover_measurement(rule, 5, period)
        self.assertLess(abs(recovered - measured), 0.001 * abs(measured))


class PeriodRecovery(unittest.TestCase):
    def _rules(self, period, values):
        return {
            metric: {
                "value": round_3g(pad(value, period, rules_corpus.PERIOD_PADDING[metric]))
            }
            for metric, value in values.items()
        }

    def test_period_is_the_minimum_bound(self):
        period = 380.0
        rules = self._rules(
            period,
            {
                "globalroute__timing__setup__ws": -8.8,
                "globalroute__timing__hold__ws": 4.0,
                "globalroute__timing__setup__tns": -120.0,
                "globalroute__timing__hold__tns": 0.0,
            },
        )
        recovered, witnesses, _ = rules_corpus.recover_period(rules)
        self.assertAlmostEqual(recovered, period, places=6)
        # Both closed metrics attain the bound; neither violating one does.
        self.assertEqual(witnesses, 2)

    def test_all_metrics_violating_leaves_only_an_upper_bound(self):
        period = 380.0
        rules = self._rules(
            period,
            {
                "globalroute__timing__setup__ws": -50.0,
                "globalroute__timing__hold__ws": -20.0,
            },
        )
        recovered, witnesses, _ = rules_corpus.recover_period(rules)
        # Nothing closed, so the minimum bound overshoots and says so by
        # having exactly one witness.
        self.assertGreater(recovered, period)
        self.assertEqual(witnesses, 1)

    def test_no_timing_rules_is_not_a_period(self):
        recovered, witnesses, bounds = rules_corpus.recover_period({})
        self.assertIsNone(recovered)
        self.assertEqual(witnesses, 0)
        self.assertEqual(bounds, {})

    def test_a_zero_period_file_carries_no_bound(self):
        # genRuleFile falls back to period = 0 when the metrics carry no
        # clock, and (1) degenerates to rule = min(m, 0). A non-negative
        # metric then writes 0, which is not a bound.
        self.assertIsNone(rules_corpus.period_bound(0.0, 5))
        self.assertIsNone(rules_corpus.period_bound(1.5, 5))


class ClockFromSdc(unittest.TestCase):
    def test_set_clk_period(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "constraint.sdc"), "w") as handle:
                handle.write("set clk_name clk\nset clk_period 380\n")
            period, source = rules_corpus.clock_from_sdc(directory)
        self.assertEqual(period, 380.0)
        self.assertEqual(source, "constraint.sdc")

    def test_literal_create_clock(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "constraint.sdc"), "w") as handle:
                handle.write('create_clock -name "tclk" -period 1000.0 [get_ports clk]\n')
            period, _ = rules_corpus.clock_from_sdc(directory)
        self.assertEqual(period, 1000.0)

    def test_unresolvable_period_is_reported_not_guessed(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "constraint.sdc"), "w") as handle:
                handle.write("create_clock -period $::env(CLK) [get_ports clk]\n")
            period, reason = rules_corpus.clock_from_sdc(directory)
        self.assertIsNone(period)
        self.assertIn("no literal period", reason)


if __name__ == "__main__":
    unittest.main()
