"""The repair screen, against a real table with a real rollback in it.

The fixture is an untouched excerpt of `asap7/gcd` seed 21's global
route log. It was chosen because it contains the three things the screen
has to get right at once: a mid-table dip, a rollback that undoes it
(the pin-swap count falls from 8 to 3 within iteration 10), and a net
endpoint-TNS that ends worse than it started while WNS ends better.
"""

import os
import unittest

import repair_delta

FIXTURE = os.path.join(os.path.dirname(__file__), "testdata", "grt_repair_rollback.log")


def fixture():
    with open(FIXTURE) as handle:
        return handle.read()


class ParseRows(unittest.TestCase):
    def test_rows_and_columns(self):
        rows = repair_delta.parse_rows(fixture())
        self.assertGreater(len(rows), 10)
        first = rows[0]
        self.assertEqual(first["iter"], "0")
        self.assertEqual(first["mark"], "*")
        self.assertAlmostEqual(first["wns"], -50.250)
        self.assertAlmostEqual(first["sttns"], -428.4)
        self.assertAlmostEqual(first["entns"], -150.8)
        self.assertEqual(first["viol"], 8)
        self.assertEqual(rows[-1]["iter"], "final")

    def test_the_rollback_is_visible_as_a_falling_move_count(self):
        # Iteration 10 prints twice: eight pin swaps at a worse WNS, then
        # three at a better one. A screen that read the dip as damage
        # would be reading the resizer's search, not the design.
        rows = repair_delta.parse_rows(fixture())
        tried = [row for row in rows if row["iter"] == "10"]
        self.assertEqual([row["swaps"] for row in tried], [8, 3])
        self.assertLess(tried[0]["wns"], tried[1]["wns"])


class Summarize(unittest.TestCase):
    def test_net_and_excursion_are_different_answers(self):
        summary = repair_delta.summarize_log(fixture())[0]
        self.assertGreater(summary["wns"]["net"], 0)
        self.assertLess(summary["wns"]["excursion"], 0)
        self.assertEqual(summary["wns"]["excursion_iter"], "10")

    def test_regression_is_reported_per_metric(self):
        summary = repair_delta.summarize_log(fixture())[0]
        # Endpoint TNS ends worse while WNS and startpoint TNS end
        # better: the whole reason `regressed` is a list.
        self.assertEqual(summary["regressed"], ["entns"])
        self.assertLess(summary["entns"]["net"], 0)
        self.assertGreater(summary["sttns"]["net"], 0)

    def test_moves_come_from_the_final_row(self):
        summary = repair_delta.summarize_log(fixture())[0]
        self.assertEqual(summary["moves"]["inserted"], 4)
        self.assertEqual(summary["moves"]["removed"], 1)

    def test_invocation_is_attributed(self):
        summary = repair_delta.summarize_log(fixture())[0]
        self.assertIn("repair_timing", summary["invocation"])

    def test_a_log_with_no_table_summarizes_to_nothing(self):
        self.assertEqual(repair_delta.summarize_log("nothing to see"), [])


if __name__ == "__main__":
    unittest.main()
