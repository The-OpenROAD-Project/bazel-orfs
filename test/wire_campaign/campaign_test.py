"""The ledger keeps one row per point, and `next` samples where the
period changes most and stops where the seeds cannot tell the ends apart."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import campaign  # noqa: E402


def row(period, floor=1000.0):
    return {
        "period_ps": period,
        "floor_ps": floor,
        "hpwl_m": 1.0,
        "worst_wire_um": 100.0,
        "rudy_top2_congestion": None,
        "steps": {},
    }


class CampaignTest(unittest.TestCase):
    def ledger(self, pts, arm="A0"):
        ledger = {"rows": []}
        for density, periods in pts.items():
            for seed, period in enumerate(periods):
                campaign.add(ledger, arm, density, seed, row(period))
        return ledger

    def test_ends_first(self):
        self.assertEqual(campaign.next_densities(self.ledger({}), "A0"), [0.2, 0.7])
        self.assertEqual(
            campaign.next_densities(self.ledger({0.2: [3000]}), "A0"), [0.7]
        )

    def test_split_where_it_moves(self):
        ledger = self.ledger({0.2: [3000], 0.45: [2900], 0.7: [2000]})
        nxt = campaign.next_densities(ledger, "A0")
        # 0.2 to 0.45 is inside the noise; 0.45 to 0.7 is where it moves.
        self.assertEqual(len(nxt), 1)
        self.assertTrue(0.45 < nxt[0] < 0.7, nxt)

    def test_inside_the_noise_is_done(self):
        ledger = self.ledger({0.2: [3000, 3100, 2950], 0.7: [3050, 2980, 3080]})
        self.assertEqual(campaign.next_densities(ledger, "A0"), [])

    def test_finest_step(self):
        ledger = self.ledger(
            {d: [3000 - 2000 * d] for d in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7)}
        )
        self.assertEqual(campaign.next_densities(ledger, "A0"), [])

    def test_add_replaces_and_survives_a_round_trip(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as d:
            results = os.path.join(d, "results.json")
            probe = os.path.join(d, "row.json")
            for period in (3000, 2500):
                with open(probe, "w") as f:
                    json.dump(row(period), f)
                campaign.main(
                    [
                        "add",
                        "--results",
                        results,
                        "--arm",
                        "A0",
                        "--density",
                        "0.2",
                        probe,
                    ]
                )
            ledger = campaign.load(results)
            self.assertEqual(len(ledger["rows"]), 1)
            self.assertEqual(ledger["rows"][0]["period_ps"], 2500)
            self.assertIn("| A0 | 0.20 | 1 | 2500 |", campaign.table(ledger))


if __name__ == "__main__":
    unittest.main()
