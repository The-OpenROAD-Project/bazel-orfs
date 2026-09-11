"""The trajectory parser and the exchange-rate screen.

The fixture is an untouched excerpt of `asap7/gcd` seed 21's global
placement log: two timing-driven interruptions, the Nesterov progress
table for each segment, and no divergence. It pins the thing most likely
to rot -- the GPL-0100..0110 message formats -- and it is also the
counter-example the screen has to survive, since its healthy segments do
exactly what the naive "HPWL up while overflow down" test would flag.
"""

import os
import unittest

import gpl_trajectory

FIXTURE = os.path.join(
    os.path.dirname(__file__), "testdata", "place_gp_timing_driven.log"
)


def fixture():
    with open(FIXTURE) as handle:
        return handle.read()


class ParseProgress(unittest.TestCase):
    def test_rows(self):
        rows = gpl_trajectory.parse_progress(fixture())
        self.assertGreater(len(rows), 20)
        self.assertEqual(rows[0]["iteration"], 0)
        self.assertGreater(rows[0]["overflow"], 0.0)
        self.assertGreater(rows[-1]["iteration"], rows[0]["iteration"])

    def test_timing_driven_events_are_fully_populated(self):
        events = gpl_trajectory.parse_td_events(fixture())
        self.assertEqual(len(events), 2)
        first = events[0]
        self.assertEqual(first["index"], 1)
        self.assertEqual(first["total"], 2)
        self.assertFalse(first["virtual"])
        self.assertIsNotNone(first["worst_slack"])
        self.assertIsNotNone(first["area_percent"])
        self.assertIsNotNone(first["gcells_created"])
        self.assertIsNotNone(first["target_density"])


class Signature(unittest.TestCase):
    def test_segments_are_split_at_the_interruptions(self):
        result = gpl_trajectory.signature(fixture())
        self.assertEqual(
            [segment["after_repair"] for segment in result["segments"]], [0, 1]
        )
        self.assertFalse(result["diverge_revert"])
        self.assertEqual(result["diverged_regions"], 0)

    def test_a_healthy_segment_trades_wirelength_for_legality(self):
        # HPWL rises while overflow falls. This is what every converging
        # placement does, which is why the screen is a rate and not this.
        segment = gpl_trajectory.signature(fixture())["segments"][0]
        self.assertGreater(segment["hpwl_growth"], 0.0)
        self.assertLess(segment["overflow_delta"], 0.0)
        self.assertGreater(segment["exchange_rate"], 0.0)

    def test_nothing_flags_against_its_own_rate(self):
        result = gpl_trajectory.signature(fixture())
        rates = [
            segment["exchange_rate"]
            for segment in result["segments"]
            if segment["exchange_rate"]
        ]
        baseline = sorted(rates)[len(rates) // 2]
        self.assertEqual(gpl_trajectory.flag(result["segments"], baseline), [])

    def test_an_outlying_rate_flags(self):
        result = gpl_trajectory.signature(fixture())
        segments = result["segments"]
        # A tenth of the ensemble's rate as the baseline: the same data
        # now reads as paying ten times the going price.
        baseline = min(
            segment["exchange_rate"]
            for segment in segments
            if segment["exchange_rate"]
        ) / 10.0
        # The default growth floor keeps this fixture quiet whatever the
        # baseline: its biggest segment grows ~19%, under the 25% floor.
        # That is the floor doing its job, so the flagging path is
        # exercised with the floor lowered explicitly rather than by
        # weakening the default.
        self.assertEqual(gpl_trajectory.flag(segments, baseline), [])
        flagged = gpl_trajectory.flag(segments, baseline, hpwl_growth=0.1)
        self.assertTrue(flagged)
        self.assertTrue(all(item["after_repair"] is not None for item in flagged))

    def test_no_baseline_flags_nothing(self):
        result = gpl_trajectory.signature(fixture())
        self.assertEqual(gpl_trajectory.flag(result["segments"], None), [])


if __name__ == "__main__":
    unittest.main()
