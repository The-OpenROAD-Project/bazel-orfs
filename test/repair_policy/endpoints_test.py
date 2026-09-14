#!/usr/bin/env python3
"""Tests for the Phase 0 endpoint-visit analysis, on a synthetic trace."""

import unittest

import endpoints


def visit(idx, pass0, passes, tns_in, tns_out, gain1, exit_, slack_in=-50.0, depth=10):
    return {
        "phase": "LEGACY",
        "idx": idx,
        "of": 4,
        "pass0": pass0,
        "pass1": pass0 + passes,
        "passes": passes,
        "s": 0.1 * passes,
        "slack_in": slack_in,
        "slack_out": slack_in + 1,
        "wns_in": -60.0,
        "wns_out": -60.0,
        "tns_in": tns_in,
        "tns_out": tns_out,
        "gain1": gain1,
        "gainN": gain1,
        "depth": depth,
        "cand": 3 * passes,
        "att": passes,
        "acc": 1 if tns_out > tns_in else 0,
        "buf": 0,
        "clone": 0,
        "sizeup": 0,
        "sizeupm": 0,
        "sizedn": 0,
        "swap": 0,
        "vt": 0,
        "unbuf": 0,
        "split": 0,
        "reroute": 0,
        "exit": exit_,
        "end": "e{}".format(idx),
    }


RECORD = {
    "design": "d",
    "substeps": {
        "4_1_cts": {
            "repair": [{"kind": "setup_hold"}],
            "repair_endpoints": [
                [
                    visit(
                        1, 0, 50, -1000.0, -990.0, 40, "stuck"
                    ),  # 10 ps for 50 passes
                    visit(2, 50, 50, -990.0, -990.0, 0, "no_change"),  # nothing
                    visit(
                        3, 100, 10, -990.0, -900.0, 2, "closed"
                    ),  # 90 ps for 10 passes
                    visit(4, 110, 5, -900.0, -900.0, 0, "no_change"),
                ]
            ],
        }
    },
}


class EndpointsTest(unittest.TestCase):
    def setUp(self):
        self.vs = endpoints.visits(RECORD, "4_1_cts")

    def test_gain_is_tns_bought(self):
        self.assertEqual([v["gain"] for v in self.vs], [10.0, 0.0, 90.0, 0.0])

    def test_concentration(self):
        c = endpoints.concentration(self.vs)
        self.assertEqual(c["paying"], 2)
        self.assertEqual(c["total_passes"], 115)
        # 55 of 115 passes bought nothing.
        self.assertAlmostEqual(c["zero_pass_share"], 100.0 * 55 / 115)

    def test_yield_order_reaches_the_gain_sooner(self):
        sweep, yield_order, total = endpoints.order_table(self.vs)
        self.assertEqual(total, 115)
        # Sweep order needs visits 1..3 (110 passes) for 90%; yield order
        # takes visit 3 first and is done in 10.
        self.assertEqual((sweep, yield_order), (110, 10))

    def test_probe_finds_the_jackpot_cheaply(self):
        table = endpoints.probe_table(self.vs)
        # Visit 1 is the phase's first endpoint and keeps its legacy budget,
        # so the probe sees visits 2-4: k=2 finds visit 3 (first gain at
        # pass 2), which is all of their gain.
        self.assertIn("| 2 | 1 | 100% |", table)
        # k=1 finds nothing.
        self.assertIn("| 1 | 0 | 0% |", table)

    def test_report_mentions_the_top_visit(self):
        text = endpoints.report("d", "4_1_cts", self.vs)
        self.assertIn("4 visits, 2 paying, 100 ps", text)
        self.assertIn("| 1 | LEGACY | 3/4 | 100 | 10 | 2 |", text)

    def test_patience_walks_the_improving_passes(self):
        vs = [dict(v) for v in self.vs]
        # Visit 1: gains at passes 1 and 40 (a 39-pass dry gap), 50 passes.
        vs[0]["imp"] = [(1, 4.0), (40, 6.0)]
        vs[1]["imp"] = []
        vs[2]["imp"] = [(2, 90.0)]
        vs[3]["imp"] = []
        table = endpoints.patience_table(vs)
        # Patience 3 keeps 94% (loses the 6 ps after the long gap); the
        # visits end 3 passes after their last gain or after 3 dry passes.
        self.assertIn("| 3 | 94.0% |", table)
        # Patience 50 keeps everything.
        self.assertIn("| 50 | 100.0% |", table)

    def test_spearman_of_a_monotone_pair_is_one(self):
        self.assertAlmostEqual(endpoints.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)


if __name__ == "__main__":
    unittest.main()
