"""crossing_report.py: sets' reports merge to one path each, a path the
sets disagree on stops, and the tables count what is over the budget."""

import os
import tempfile
import unittest

import crossing_report

HEADER = "# reg2reg paths over 150 ps\n# need_ps kind from to start end\n"


def write(d, name, lines):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(HEADER + "".join(l + "\n" for l in lines) + "crossing 0\ninside 0\n")
    return path


class CrossingReportTest(unittest.TestCase):
    def test_merges_overlapping_sets(self):
        with tempfile.TemporaryDirectory() as d:
            a = write(
                d,
                "c.0",
                [
                    "227.8 crossing u_A u_B a/q b/d u_parent",
                    "160.0 crossing u_A u_parent a/q2 p/d -",
                ],
            )
            b = write(
                d,
                "c.1",
                [
                    "227.8 crossing u_A u_B a/q b/d u_parent",
                    "120.0 inside u_B u_B b/q b/d2 -",
                ],
            )
            crossing_report.main(os.path.join(d, "out"), 150, [a, b])
            with open(os.path.join(d, "out", "crossing.txt")) as f:
                rows = [l for l in f if not l.startswith("#")]
            self.assertEqual(len(rows), 2)
            self.assertTrue(rows[0].startswith("227.8 u_A u_B"))
            with open(os.path.join(d, "out", "tables.md")) as f:
                tables = f.read()
            self.assertIn("2 crossing paths timed, 2 over 150 ps", tables)
            self.assertIn("| u_A | u_B | u_parent | 1 | 227.8 |", tables)
            self.assertIn("| passes through | paths over | worst ps |", tables)
            self.assertIn("| u_parent | 1 | 227.8 |", tables)

    def test_a_set_listing_a_path_twice_keeps_its_worst(self):
        with tempfile.TemporaryDirectory() as d:
            a = write(
                d,
                "c.0",
                [
                    "3619.3 crossing u_A u_B a/q b/d -",
                    "3595.1 crossing u_A u_B a/q b/d -",
                ],
            )
            b = write(d, "c.1", ["3619.3 crossing u_A u_B a/q b/d -"])
            crossing_report.main(os.path.join(d, "out"), 2000, [a, b])
            with open(os.path.join(d, "out", "crossing.txt")) as f:
                rows = [l for l in f if not l.startswith("#")]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].startswith("3619.3"))

    def test_disagreeing_sets_stop(self):
        with tempfile.TemporaryDirectory() as d:
            a = write(d, "c.0", ["227.8 crossing u_A u_B a/q b/d"])
            b = write(d, "c.1", ["226.0 crossing u_A u_B a/q b/d"])
            with self.assertRaises(SystemExit):
                crossing_report.main(os.path.join(d, "out"), 150, [a, b])

    def test_matches_the_whole_design(self):
        with tempfile.TemporaryDirectory() as d:
            sets = os.path.join(d, "sets")
            os.mkdir(sets)
            write(sets, "cross.txt.0", ["227.8 crossing u_A u_B a/q b/d -"])
            write(sets, "cross.txt.1", ["160.0 crossing u_C u_parent c/q p/d -"])
            whole = write(
                d,
                "whole",
                [
                    "227.8 crossing u_A u_B a/q b/d -",
                    "160.0 crossing u_C u_parent c/q p/d -",
                    "300.0 inside u_A u_A a/q a/d -",
                ],
            )
            crossing_report.main(os.path.join(d, "out"), 150, [sets], whole)

    def test_a_path_the_sets_missed_stops(self):
        with tempfile.TemporaryDirectory() as d:
            a = write(d, "c.0", ["227.8 crossing u_A u_B a/q b/d -"])
            whole = write(
                d,
                "whole",
                [
                    "227.8 crossing u_A u_B a/q b/d -",
                    "160.0 crossing u_C u_parent c/q p/d -",
                ],
            )
            with self.assertRaises(SystemExit):
                crossing_report.main(os.path.join(d, "out"), 150, [a], whole)


if __name__ == "__main__":
    unittest.main()
