"""crossing_report.py: sets' reports merge to one path each, a path the
sets disagree on stops, and the tables count what is over the budget."""

import os
import tempfile
import unittest

import crossing_report

HEADER = "# reg2reg paths over 150 ps\n# need_ps kind from to start end\n"

# u_P is the parent (u_parent in the tests of --whole): no set names it,
# every set holds it


def write(d, name, lines):
    """A report as crossing_paths.tcl writes one: it ends with the count
    of its crossing rows and of its inside rows."""
    path = os.path.join(d, name)
    counts = "".join(
        "%s %d\n" % (kind, sum(l.split()[1] == kind for l in lines))
        for kind in ("crossing", "inside")
    )
    with open(path, "w") as f:
        f.write(HEADER + "".join(l + "\n" for l in lines) + counts)
    return path


def sets(d, *blocks):
    """crossing_plan.tcl's sets file: a comment, then a set per line."""
    path = os.path.join(d, "sets.txt")
    with open(path, "w") as f:
        f.write("# one set per line: every signature is held by one of them\n")
        f.write("".join(b + "\n" for b in blocks))
    return path


def rows(d):
    with open(os.path.join(d, "out", "crossing.txt")) as f:
        return [l for l in f if not l.startswith("#")]


class CrossingReportTest(unittest.TestCase):
    def report(self, d, sets_path, paths, budget=2000, whole=None):
        crossing_report.main(os.path.join(d, "out"), budget, sets_path, paths, whole)
        return rows(d)

    def stops(self, d, sets_path, paths, why, budget=2000, whole=None):
        """The report stops, and for the reason the test is about."""
        with self.assertRaises(SystemExit) as e:
            self.report(d, sets_path, paths, budget, whole)
        self.assertIn(why, str(e.exception))

    def test_merges_overlapping_sets(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B u_C", "u_A u_B u_D")
            a = write(
                d,
                "c.0",
                [
                    "227.8 crossing u_A u_B a/q b/d u_parent",
                    "160.0 crossing u_C u_parent c/q p/d -",
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
            got = self.report(d, s, [a, b], budget=150)
            self.assertEqual(len(got), 2)
            self.assertTrue(got[0].startswith("227.8 u_A u_B"))
            with open(os.path.join(d, "out", "tables.md")) as f:
                tables = f.read()
            self.assertIn("2 crossing paths timed, 2 over 150 ps", tables)
            self.assertIn("| u_A | u_B | u_parent | 1 | 227.8 |", tables)
            self.assertIn("| passes through | paths over | worst ps |", tables)
            self.assertIn("| u_parent | 1 | 227.8 |", tables)

    def test_a_set_listing_a_path_twice_keeps_its_worst(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B")
            a = write(
                d,
                "c.0",
                [
                    "3595.1 crossing u_A u_B a/q b/d -",
                    "3619.3 crossing u_A u_B a/q b/d -",
                ],
            )
            got = self.report(d, s, [a])
            self.assertEqual(len(got), 1)
            self.assertTrue(got[0].startswith("3619.3"))

    def test_disagreeing_sets_stop(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B u_C", "u_A u_B u_D")
            a = write(d, "c.0", ["227.8 crossing u_A u_B a/q b/d"])
            b = write(d, "c.1", ["226.0 crossing u_A u_B a/q b/d"])
            self.stops(
                d,
                s,
                [a, b],
                "needs 227.8 ps in set 0 (u_A u_B u_C); "
                "set 1 (u_A u_B u_D) lists it at 226.0 ps",
                budget=150,
            )

    def test_a_path_through_a_third_block_is_another_path(self):
        # XSTile run 27: MemBlock's s2Valid into a parent register needs
        # 3,411.8 ps through Flt and 2,437.6 ps directly. The set holding
        # Flt lists both; three sets with MemBlock and no Flt list the
        # direct one alone (the fourth lists a worse path inside the
        # parent into that endpoint), and that is not the sets disagreeing
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_F u_M")
            a = write(d, "c.0", ["2437.6 crossing u_M u_P m/q p/d - ^^"])
            b = write(
                d,
                "c.1",
                [
                    "3411.8 crossing u_M u_P m/q p/d u_F ^^",
                    "2437.6 crossing u_M u_P m/q p/d - ^^",
                ],
            )
            self.assertEqual(
                self.report(d, s, [a, b]), ["3411.8 u_M u_P u_F m/q p/d\n"]
            )

    def test_a_path_hidden_by_the_same_start_through_a_block(self):
        # not seen in run 27, where the set holding Flt lists both: a set
        # that lists the path through the third block alone shows a path
        # that bad into the endpoint, which is all that is asked of it
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_F u_M")
            a = write(d, "c.0", ["2437.6 crossing u_M u_P m/q p/d - ^^"])
            b = write(d, "c.1", ["3411.8 crossing u_M u_P m/q p/d u_F ^^"])
            self.assertEqual(
                self.report(d, s, [a, b]), ["3411.8 u_M u_P u_F m/q p/d\n"]
            )

    def test_a_path_hidden_by_a_worse_start_is_not_a_disagreement(self):
        # XSTile run 25: the set holding u_Rob listed the flush register
        # into an Flt endpoint at 2,313.6 ps only, its 2,327.6 ps variant
        # pushed out by Rob's state at 2,337.2 ps into the same endpoint
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_F u_M", "u_F u_R")
            a = write(
                d,
                "c.0",
                [
                    "2327.6 crossing u_P u_F p/q f/d - ^v",
                    "2313.6 crossing u_P u_F p/q f/d - ^v",
                ],
            )
            b = write(
                d,
                "c.1",
                [
                    "2337.2 crossing u_R u_F r/q f/d u_P vv",
                    "2313.6 crossing u_P u_F p/q f/d - ^v",
                ],
            )
            got = self.report(d, s, [a, b])
            self.assertEqual(len(got), 2)
            self.assertTrue(got[0].startswith("2337.2 u_R u_F"))
            self.assertTrue(got[1].startswith("2327.6 u_P u_F"))

    def test_a_lower_path_without_a_worse_start_stops(self):
        # the other start into the endpoint needs less than the path's
        # time in the other set, so it cannot have hidden it
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_F u_M", "u_F u_R")
            a = write(d, "c.0", ["2327.6 crossing u_P u_F p/q f/d - ^v"])
            b = write(
                d,
                "c.1",
                [
                    "2320.0 crossing u_R u_F r/q f/d - vv",
                    "2313.6 crossing u_P u_F p/q f/d - ^v",
                ],
            )
            self.stops(
                d,
                s,
                [a, b],
                "set 1 (u_F u_R) lists it at 2313.6 ps, and the worst path "
                "it lists into that endpoint needs 2320.0 ps",
            )

    def test_a_path_inside_one_macro_hides_a_crossing(self):
        # XSTile run 27: Rob's state into the parent's decode buffer,
        # 3,848.6 ps, is listed by two of the four sets holding Rob; the
        # other two list a path inside the parent into that endpoint,
        # 3,916.0 ps, which only they time
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_R u_V")
            a = write(d, "c.0", ["3848.6 crossing u_R u_P r/q p/d - ^^"])
            b = write(d, "c.1", ["3916.0 inside u_P u_P p/q p/d - ^^"])
            self.assertEqual(self.report(d, s, [a, b]), ["3848.6 u_R u_P - r/q p/d\n"])

    def test_a_set_that_holds_a_path_and_does_not_show_it_stops(self):
        # the path inside the parent needs less than the crossing, so it
        # did not push it out: the set lost a path it should have timed
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_R u_V")
            a = write(d, "c.0", ["3848.6 crossing u_R u_P r/q p/d - ^^"])
            b = write(d, "c.1", ["3000.0 inside u_P u_P p/q p/d - ^^"])
            self.stops(
                d,
                s,
                [a, b],
                "r/q -> p/d through - needs 3848.6 ps in set 0 (u_M u_R); "
                "set 1 (u_R u_V) holds its blocks and does not list it, and "
                "the worst path it lists into that endpoint needs 3000.0 ps",
            )

    def test_a_set_holding_exactly_a_paths_blocks_owes_it(self):
        # XSTile's sets are pairs of blocks: a crossing between the two
        # is owed by the set that is that pair, not only by a larger one
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", "u_A u_C")
            a = write(d, "c.0", [])
            b = write(d, "c.1", ["2500.0 crossing u_A u_B a/q b/d - ^^"])
            self.stops(
                d, s, [a, b], "set 0 (u_A u_B) holds its blocks and does not list it"
            )

    def test_a_set_without_a_paths_blocks_need_not_list_it(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_F u_V")
            a = write(d, "c.0", ["3848.6 crossing u_R u_P r/q p/d - ^^"])
            b = write(d, "c.1", [])
            self.assertEqual(len(self.report(d, s, [a, b])), 1)

    def test_a_set_listing_a_path_it_does_not_hold_must_agree(self):
        # a register of a block outside the set, right on a crossing net,
        # is kept to capture (crossing_cones): the set can list the path,
        # and then answers for it as a set holding its blocks does. The
        # cut also leaves a one- or two-cell feedthrough through a block
        # the set does not hold, timed without its side inputs: a stop of
        # this shape on such a path is the cut, not the timing
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", "u_A u_C")
            a = write(d, "c.0", ["2500.0 crossing u_A u_C a/q c/d - ^^"])
            b = write(d, "c.1", ["2500.0 crossing u_A u_C a/q c/d - ^^"])
            self.assertEqual(len(self.report(d, s, [a, b])), 1)
            a = write(d, "c.0", ["2400.0 crossing u_A u_C a/q c/d - ^^"])
            self.stops(d, s, [a, b], "set 0 (u_A u_B) lists it at 2400.0 ps")

    def test_a_set_without_the_third_block_answers_for_the_direct_one(self):
        # the set without the third block lists the direct path lower
        # than the set holding the block does, and nothing worse into the
        # endpoint: the other set's path through the block is no excuse
        # for it (a worse path of its own into the endpoint would be)
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_F u_M")
            a = write(d, "c.0", ["2400.0 crossing u_M u_P m/q p/d - ^^"])
            b = write(
                d,
                "c.1",
                [
                    "3411.8 crossing u_M u_P m/q p/d u_F ^^",
                    "2437.6 crossing u_M u_P m/q p/d - ^^",
                ],
            )
            self.stops(
                d,
                s,
                [a, b],
                "m/q -> p/d through - needs 2437.6 ps in set 1 (u_F u_M); "
                "set 0 (u_M u_R) lists it at 2400.0 ps",
            )

    def test_an_endpoints_worst_is_not_its_first_row(self):
        # test_a_path_hidden_by_a_worse_start_is_not_a_disagreement, set
        # 0 listing the path once and set 1's rows in the other order
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_F u_M", "u_F u_R")
            a = write(d, "c.0", ["2327.6 crossing u_P u_F p/q f/d - ^v"])
            b = write(
                d,
                "c.1",
                [
                    "2313.6 crossing u_P u_F p/q f/d - ^v",
                    "2337.2 crossing u_R u_F r/q f/d u_P vv",
                ],
            )
            self.assertEqual(len(self.report(d, s, [a, b])), 2)

    def test_a_path_through_two_blocks_needs_both_held(self):
        # through_macros is a comma list: a set holding one of the two
        # did not time the path, and the tables count it under each
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_F u_V", "u_M u_V")
            a = write(d, "c.0", ["2500.0 crossing u_P u_P p/q p/d u_F,u_V ^^"])
            b = write(d, "c.1", [])
            self.assertEqual(len(self.report(d, s, [a, b])), 1)
            with open(os.path.join(d, "out", "tables.md")) as f:
                tables = f.read()
            self.assertIn("| u_F | 1 | 2500.0 |", tables)
            self.assertIn("| u_V | 1 | 2500.0 |", tables)

    def test_a_path_through_two_blocks_is_owed_by_a_set_holding_both(self):
        # each block of the comma list is touched: no set holding both is
        # the plan and the reports disagreeing, and a set holding both
        # answers for the path
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_F u_M", "u_M u_V")
            a = write(d, "c.0", ["2500.0 crossing u_P u_P p/q p/d u_F,u_V ^^"])
            b = write(d, "c.1", [])
            self.stops(d, s, [a, b], "no set holds its blocks (u_F u_V)")
            s = sets(d, "u_F u_M", "u_F u_V")
            self.stops(
                d, s, [a, b], "set 1 (u_F u_V) holds its blocks and does not list it"
            )

    def test_a_path_through_a_top_level_cell_is_owed_by_no_set(self):
        # crossing_paths.tcl names a cell of the top level after itself:
        # no set names it, and no set's cones are seeded from its nets,
        # so a set that does not list the path did not lose it
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A", "u_B")
            a = write(d, "c.0", ["3000.0 crossing u_P u_P p/q p/d rebuffer7 ^^"])
            b = write(d, "c.1", [])
            self.assertEqual(len(self.report(d, s, [a, b])), 1)
            b = write(d, "c.1", ["2900.0 crossing u_P u_P p/q p/d rebuffer7 ^^"])
            self.stops(d, s, [a, b], "set 1 (u_B) lists it at 2900.0 ps")

    def test_a_path_whose_blocks_no_set_holds_stops(self):
        # crossing_plan.tcl plans a set for every path's blocks: a set
        # listing a path between two blocks no set holds together is the
        # plan and the reports disagreeing
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", "u_A u_C")
            a = write(d, "c.0", ["2500.0 crossing u_B u_C b/q c/d - ^^"])
            b = write(d, "c.1", [])
            self.stops(
                d,
                s,
                [a, b],
                "b/q -> c/d through -, 2500.0 ps in set 0 (u_A u_B): "
                "no set holds its blocks (u_B u_C)",
            )

    def test_a_path_a_written_digit_over_the_budget_can_go_unlisted(self):
        # a set lists what needs the budget or more: 2,000.1 ps in one set
        # can be 2,000.0 or 1,999.9 in another, written or not
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_R u_V")
            a = write(d, "c.0", ["2000.1 crossing u_R u_P r/q p/d - ^^"])
            b = write(d, "c.1", [])
            self.assertEqual(len(self.report(d, s, [a, b])), 1)
            a = write(d, "c.0", ["2000.2 crossing u_R u_P r/q p/d - ^^"])
            self.stops(d, s, [a, b], "holds its blocks and does not list it")

    def test_sets_agreeing_to_the_written_digit_merge(self):
        # XSTile run 26: Rob's state into the parent's decode buffer at
        # 2,941.5 ps in one set and 2,941.4 in another, the same path
        # rounded to the 0.1 ps crossing_paths.tcl writes
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_R u_V")
            a = write(d, "c.0", ["2941.5 crossing u_R u_P r/q p/d - vv"])
            b = write(d, "c.1", ["2941.4 crossing u_R u_P r/q p/d - vv"])
            got = self.report(d, s, [a, b])
            self.assertEqual(len(got), 1)
            self.assertTrue(got[0].startswith("2941.5"))

    def test_sets_two_digits_apart_still_stop(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_M u_R", "u_R u_V")
            a = write(d, "c.0", ["2941.5 crossing u_R u_P r/q p/d - vv"])
            b = write(d, "c.1", ["2941.3 crossing u_R u_P r/q p/d - vv"])
            self.stops(d, s, [a, b], "set 1 (u_R u_V) lists it at 2941.3 ps")

    def test_a_report_is_its_sets_by_number_not_by_position(self):
        # read as the first set's, c.1 would list a path of a block its
        # set does not hold, and c.0 would hold it and not list it
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", "u_C")
            a = write(d, "c.0", ["2500.0 crossing u_A u_B a/q b/d - ^^"])
            b = write(d, "c.1", ["2400.0 crossing u_C u_P c/q p/d - ^^"])
            self.assertEqual(len(self.report(d, s, [b, a])), 2)

    def test_every_set_has_one_report(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", "u_C")
            a = write(d, "c.0", ["2500.0 crossing u_A u_B a/q b/d - ^^"])
            self.stops(d, s, [a], "set 1 (u_C) has no report")
            twice = write(d, "again.0", [])
            b = write(d, "c.1", [])
            self.stops(d, s, [a, b, twice], "set 0 has two reports")
            c = write(d, "c.2", [])
            self.stops(d, s, [a, b, c], "is the report of none of the 2 sets")
            unnumbered = write(d, "cross.txt", [])
            self.stops(d, s, [unnumbered], "is the report of none of the 2 sets")

    def test_a_blank_line_in_the_sets_is_no_set(self):
        # crossing_time_sets.tcl numbers the sets skipping blank lines
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", "", "u_C")
            a = write(d, "c.0", ["2500.0 crossing u_A u_B a/q b/d - ^^"])
            b = write(d, "c.1", ["2400.0 crossing u_C u_P c/q p/d - ^^"])
            self.assertEqual(len(self.report(d, s, [a, b])), 2)

    def test_a_comment_in_the_sets_starts_its_line(self):
        # crossing_time_sets.tcl takes "#" for a comment in the first
        # column only: an indented one is a set there, and so here, or
        # every later report would be read against another set's blocks
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", " # u_Z", "u_C")
            a = write(d, "c.0", ["2500.0 crossing u_A u_B a/q b/d - ^^"])
            b = write(d, "c.1", [])
            c = write(d, "c.2", ["2400.0 crossing u_C u_P c/q p/d - ^^"])
            self.assertEqual(len(self.report(d, s, [a, b, c])), 2)

    def test_a_report_cut_short_stops(self):
        # crossing_paths.tcl ends a report with its two counts: without
        # them, without one of them, or with other rows of either kind
        # than they count, paths are missing
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B")
            row = "2500.0 crossing u_A u_B a/q b/d - ^^\n"
            a = os.path.join(d, "c.0")
            with open(a, "w") as f:
                f.write(HEADER + row)
            self.stops(
                d, s, [a], "has 1 crossing and 0 inside rows, and it ends counting none"
            )
            with open(a, "w") as f:
                f.write(HEADER + row + "crossing 2\ninside 0\n")
            self.stops(d, s, [a], "ends counting 2 crossing and 0 inside")
            with open(a, "w") as f:
                f.write(HEADER + row + "crossing 1\ninside 1\n")
            self.stops(d, s, [a], "ends counting 1 crossing and 1 inside")
            with open(a, "w") as f:
                f.write(HEADER + row + "crossing 1\n")
            self.stops(d, s, [a], "and it ends counting 1 crossing: cut short")
            with open(a, "w") as f:
                f.write(HEADER + row + "crossing 1\ninside 0\n")
            self.assertEqual(len(self.report(d, s, [a])), 1)

    def test_a_line_that_is_no_row_stops(self):
        # a row cut in the middle is not skipped
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B")
            a = write(
                d,
                "c.0",
                ["2500.0 crossing u_A u_B a/q b/d - ^^", "2400.0 crossing u_A u_B a/q"],
            )
            self.stops(
                d, s, [a], "neither a row nor a count: 2400.0 crossing u_A u_B a/q"
            )

    def test_a_row_of_another_shape_stops(self):
        # a field too many, a kind that is neither, a count with a tail
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B")
            for bad in (
                "2500.0 crossing u_A u_B a/q b/d - ^^ x",
                "2500.0 crosing u_A u_B a/q b/d - ^^",
                "crossing 1 x",
            ):
                a = os.path.join(d, "c.0")
                with open(a, "w") as f:
                    f.write(HEADER + bad + "\ncrossing 0\ninside 0\n")
                self.stops(d, s, [a], "neither a row nor a count: " + bad)

    def test_a_directory_is_its_reports_and_nothing_else(self):
        # crossing_paths.tcl writes crossing_data.<n>.tsv beside
        # cross.txt.<n> (CROSSING_DATA_MIN_PS)
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B")
            reports = os.path.join(d, "time")
            os.mkdir(reports)
            write(reports, "cross.txt.0", ["2500.0 crossing u_A u_B a/q b/d - ^^"])
            with open(os.path.join(reports, "crossing_data.0.tsv"), "w") as f:
                f.write("# crossing paths over 1500 ps\n2500.0\t0.0\tu_A\tu_B\n")
            self.assertEqual(len(self.report(d, s, [reports])), 1)

    def test_matches_the_whole_design(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B", "u_C")
            reports = os.path.join(d, "time")
            os.mkdir(reports)
            write(reports, "cross.txt.0", ["227.8 crossing u_A u_B a/q b/d -"])
            write(reports, "cross.txt.1", ["160.0 crossing u_C u_parent c/q p/d -"])
            whole = write(
                d,
                "whole",
                [
                    "227.8 crossing u_A u_B a/q b/d -",
                    "160.0 crossing u_C u_parent c/q p/d -",
                    "300.0 inside u_A u_A a/q a/d -",
                ],
            )
            self.report(d, s, [reports], budget=150, whole=whole)

    def test_a_path_the_sets_missed_stops(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B")
            a = write(d, "c.0", ["227.8 crossing u_A u_B a/q b/d -"])
            whole = write(
                d,
                "whole",
                [
                    "227.8 crossing u_A u_B a/q b/d -",
                    "160.0 crossing u_C u_parent c/q p/d -",
                ],
            )
            self.stops(
                d, s, [a], "c/q -> p/d: only timed whole", budget=150, whole=whole
            )

    def test_a_need_the_whole_design_does_not_share_stops(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B")
            a = write(d, "c.0", ["227.5 crossing u_A u_B a/q b/d -"])
            whole = write(d, "whole", ["227.8 crossing u_A u_B a/q b/d -"])
            self.stops(
                d,
                s,
                [a],
                "a/q -> b/d: 227.5 ps in the sets, 227.8 ps whole",
                budget=150,
                whole=whole,
            )

    def test_the_whole_design_listing_two_routes_is_its_worst(self):
        with tempfile.TemporaryDirectory() as d:
            s = sets(d, "u_A u_B u_C")
            lines = [
                "300.0 crossing u_A u_B a/q b/d u_C",
                "227.8 crossing u_A u_B a/q b/d -",
            ]
            a = write(d, "c.0", lines)
            whole = write(d, "whole", lines)
            self.report(d, s, [a], budget=150, whole=whole)


if __name__ == "__main__":
    unittest.main()
