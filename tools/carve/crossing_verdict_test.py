"""crossing_verdict.py: a second pass moved the crossings when at least 10 %
fewer pairs are over the budget or the worst crossing is at least 5 % of the
budget better, and did nothing otherwise; what it cannot judge it stops on
or reports."""

import os
import subprocess
import sys
import tempfile
import unittest

import crossing_verdict

CROSSING_HEADER = "# need_ps from_macro to_macro through_macros startpoint endpoint\n"


def rows_of(needs, frm="u_A", to="u_B", through="-", prefix="p"):
    """crossing_report.py's rows, one pair of registers per need, named by
    its place in the list."""
    return [
        (need, frm, to, through, "%s%d/q" % (prefix, i), "%s%d/d" % (prefix, i))
        for i, need in enumerate(needs)
    ]


def as_dict(rows):
    """What read_crossing returns."""
    return {(r[4], r[5]): (r[0], r[1], r[2], r[3]) for r in rows}


def write_crossing(d, name, rows):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(CROSSING_HEADER)
        for need, frm, to, through, start, end in rows:
            f.write("%.1f %s %s %s %s %s\n" % (need, frm, to, through, start, end))
    return path


def write_sets(d, name, sets):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write("# one set per line: every signature is held by one of them\n")
        for blocks in sets:
            f.write(blocks + "\n")
    return path


def write_time(d, inside):
    """A crossing_time directory of one set: crossing_paths.tcl's report, a
    row per (need, macro) inside a macro, then its counts."""
    os.makedirs(d, exist_ok=True)
    seen = {}
    with open(os.path.join(d, "cross.txt.0"), "w") as f:
        f.write("# reg2reg paths over 150 ps at global route; period 1000 ps\n")
        f.write(
            "# need_ps kind from_macro to_macro startpoint endpoint through_macros "
            "slot\n"
        )
        for need, macro in inside:
            n = seen[macro] = seen.get(macro, -1) + 1
            f.write(
                "%.1f inside %s %s %s_%d/q %s_%d/d - 0\n"
                % (need, macro, macro, macro, n, macro, n)
            )
        f.write("crossing 0\ninside %d\n" % len(inside))
    return d


def moving(budget, firm_worst, firm_n=100):
    """The first pass's pairs, firm_n over the budget, one at firm_worst."""
    return [firm_worst] + [budget + 10.0] * (firm_n - 1)


class VerdictRuleTest(unittest.TestCase):
    """compare(): the rule, on pairs and worsts alone."""

    def name(self, budget, firm, final):
        return crossing_verdict.verdict_name(
            crossing_verdict.compare(
                as_dict(rows_of(firm)), as_dict(rows_of(final)), budget
            )
        )

    def test_the_four_corners(self):
        firm = moving(2000, 3000.0)
        cases = [
            # (pairs left over the budget, worst, verdict)
            (80, 2800.0, "moved the crossings"),  # fewer pairs and a better worst
            (89, 2950.0, "moved the crossings"),  # fewer pairs alone
            (100, 2800.0, "moved the crossings"),  # a better worst alone
            (100, 3000.0, "DID NOTHING"),  # neither
        ]
        for left, worst, want in cases:
            final = moving(2000, worst, left)
            self.assertEqual(self.name(2000, firm, final), want, (left, worst))

    def test_the_edges_of_the_rule_at_2000_ps(self):
        firm = moving(2000, 3000.0)
        cases = [
            (90, 2950.0, "moved the crossings"),  # 10 % fewer exactly
            (91, 2950.0, "DID NOTHING"),  # 9 % fewer
            (100, 2900.0, "moved the crossings"),  # 100 ps better exactly: 5 %
            (100, 2900.1, "DID NOTHING"),  # 99.9 ps
            (101, 3100.0, "DID NOTHING"),  # more pairs, a worse worst
        ]
        for left, worst, want in cases:
            final = moving(2000, worst, left)
            self.assertEqual(self.name(2000, firm, final), want, (left, worst))

    def test_the_two_shares_are_not_added_up(self):
        # 9.9 % fewer pairs with a worst 4.9 % of the budget better is under
        # both and does nothing
        firm = moving(2000, 3000.0, 1000)
        final = moving(2000, 3000.0 - 98.0, 901)
        self.assertEqual(self.name(2000, firm, final), "DID NOTHING")

    def test_the_rule_is_a_share_of_the_budget(self):
        # 5 % of 150 ps is 7.5 ps, and needs are written to 0.1 ps: 256.4
        # less 248.9 is 7.5, though doubles make it 7.499999999999972
        firm = moving(150, 256.4)
        cases = [
            (248.9, "moved the crossings"),
            (248.8, "moved the crossings"),
            (249.0, "DID NOTHING"),  # 7.4 ps
        ]
        for worst, want in cases:
            self.assertEqual(self.name(150, firm, moving(150, worst)), want, worst)

    def test_a_report_against_itself_does_nothing(self):
        firm = moving(150, 201.4)
        report = as_dict(rows_of(firm))
        v = crossing_verdict.compare(report, report, 150)
        self.assertFalse(v.moved)
        self.assertEqual(v.better, 0.0)
        self.assertEqual(v.fewer_pct, 0.0)

    def test_no_pair_left_over_the_budget_moved_them_all(self):
        # a final report with rows, none over the budget, and one with none
        firm = as_dict(rows_of(moving(150, 201.4)))
        for final in (as_dict(rows_of([150.0, 120.0])), {}):
            v = crossing_verdict.compare(firm, final, 150)
            self.assertTrue(v.moved)
            self.assertEqual(v.final_over, 0)
            self.assertEqual(v.fewer_pct, 100.0)

    def test_an_empty_final_report_names_what_is_known_of_its_worst(self):
        firm = as_dict(rows_of(moving(150, 201.4)))
        line = crossing_verdict.verdict_line(crossing_verdict.compare(firm, {}, 150))
        self.assertTrue(line.startswith("moved the crossings: "), line)
        self.assertIn("pairs by name over 150 ps: 0 (firm 100, -100.0 %)", line)
        # under the budget: at least the firm's worst less the budget better
        self.assertIn("no crossing listed (firm worst 201.4 ps, at least 51.4 ps", line)
        self.assertNotIn("0.0 ps", line)

    def test_the_line_has_both_passes_and_both_differences(self):
        firm = as_dict(rows_of(moving(150, 201.4)))
        final = as_dict(rows_of(moving(150, 191.9, 75)))
        line = crossing_verdict.verdict_line(crossing_verdict.compare(firm, final, 150))
        self.assertEqual(
            line,
            "moved the crossings: pairs by name over 150 ps: 75 (firm 100, "
            "-25.0 %), worst crossing 191.9 ps (firm 201.4, -9.5 ps)",
        )

    def test_the_share_is_cut_toward_zero(self):
        # 9.99 % fewer pairs is under the rule's 10 % and prints as under it
        firm = as_dict(rows_of(moving(2000, 3000.0, 10000)))
        final = as_dict(rows_of(moving(2000, 3000.0, 9001)))
        v = crossing_verdict.compare(firm, final, 2000)
        self.assertFalse(v.moved)
        line = crossing_verdict.verdict_line(v)
        self.assertIn("9001 (firm 10000, -9.9 %)", line)
        # one pair more of 10000 is less than 0.1 % more
        final = as_dict(rows_of(moving(2000, 3000.0, 10001)))
        line = crossing_verdict.verdict_line(
            crossing_verdict.compare(firm, final, 2000)
        )
        self.assertIn("10001 (firm 10000, +0.0 %)", line)
        # exactly 10 % fewer is the rule's and prints as it
        final = as_dict(rows_of(moving(2000, 3000.0, 9000)))
        line = crossing_verdict.verdict_line(
            crossing_verdict.compare(firm, final, 2000)
        )
        self.assertIn("9000 (firm 10000, -10.0 %)", line)

    def test_a_pair_is_its_start_and_end_by_name(self):
        # the same pair in both passes is one pair, at each pass's need
        firm = as_dict(rows_of([300.0, 300.0]))
        final = as_dict(rows_of([100.0, 300.0]))
        v = crossing_verdict.compare(firm, final, 200)
        self.assertEqual((v.firm_over, v.final_over), (2, 1))

    def test_the_tables_count_what_is_over_the_budget(self):
        firm = as_dict(
            rows_of([300.0, 250.0], "u_A", "u_B")
            + rows_of([220.0], "u_A", "u_C", "u_B", "q")
            + rows_of([100.0], "u_D", "u_B", "-", "r")
        )
        final = as_dict(rows_of([260.0], "u_A", "u_B"))
        self.assertEqual(
            crossing_verdict.group_table(firm, final, 200),
            [
                "| from | to | through | firm pairs | firm worst | final pairs "
                "| final worst |",
                "|---|---|---|---:|---:|---:|---:|",
                "| u_A | u_B | - | 2 | 300.0 | 1 | 260.0 |",
                "| u_A | u_C | u_B | 1 | 220.0 | 0 | 0.0 |",
            ],
        )


class VerdictToolTest(unittest.TestCase):
    """The tool as a command: its files, its exit status, its messages."""

    def run_tool(self, *args):
        done = subprocess.run(
            [sys.executable, crossing_verdict.__file__] + [str(a) for a in args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        return done.returncode, done.stdout, done.stderr

    def passes(self, d, budget, firm_needs, final_needs):
        firm = write_crossing(d, "firm.txt", rows_of(firm_needs))
        final = write_crossing(d, "final.txt", rows_of(final_needs))
        return str(budget), firm, final

    def test_line_1_is_the_verdict_and_the_group_table_follows(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 191.9, 70))
            status, out, err = self.run_tool(*args)
            self.assertEqual((status, err), (0, ""))
            lines = out.splitlines()
            self.assertTrue(lines[0].startswith("moved the crossings: "), lines[0])
            self.assertIn("by name", lines[0])
            self.assertIn("| u_A | u_B | - | 100 | 201.4 | 70 | 191.9 |", lines)
            # no sets or time asked for, none reported
            self.assertFalse([l for l in lines if l.startswith("sets:")])
            self.assertNotIn("inside one macro", out)

    def test_expect_moved_stops_on_a_pass_that_did_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 201.4))
            status, out, err = self.run_tool("--expect", "moved", *args)
            self.assertEqual(status, 1)
            self.assertTrue(out.startswith("DID NOTHING: "), out)
            self.assertIn(
                "expected the crossings moved, the verdict is DID NOTHING", err
            )

    def test_expect_nothing_stops_on_a_pass_that_moved(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 160.0, 50))
            status, out, err = self.run_tool("--expect", "nothing", *args)
            self.assertEqual(status, 1)
            self.assertTrue(out.startswith("moved the crossings: "), out)
            self.assertIn(
                "expected nothing moved, the verdict is moved the crossings", err
            )

    def test_expect_is_met_by_the_verdict_it_names(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 201.4))
            self.assertEqual(self.run_tool("--expect", "nothing", *args)[0], 0)
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 160.0, 50))
            self.assertEqual(self.run_tool("--expect", "moved", *args)[0], 0)

    def test_a_first_pass_with_no_pair_over_the_budget_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            cases = {
                "empty": [],
                "at the budget": [150.0, 120.0],
            }
            for why, needs in cases.items():
                args = self.passes(d, 150, needs, moving(150, 190.0))
                status, out, err = self.run_tool(*args)
                self.assertEqual(status, 1, why)
                self.assertEqual(out, "", why)
                self.assertIn(
                    "crossing_verdict: the first pass has no pair over 150 ps", err
                )
                self.assertNotIn("Traceback", err)

    def test_an_empty_final_report_moved_the_crossings(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), [])
            status, out, err = self.run_tool("--expect", "moved", *args)
            self.assertEqual((status, err), (0, ""))
            self.assertTrue(out.startswith("moved the crossings: "), out)

    def test_a_pair_listed_twice_is_kept_at_its_worst_row(self):
        with tempfile.TemporaryDirectory() as d:
            for needs in ([300.0, 200.0], [200.0, 300.0]):
                path = os.path.join(d, "twice.txt")
                with open(path, "w") as f:
                    f.write(CROSSING_HEADER)
                    for need in needs:
                        f.write("%.1f u_A u_B - p/q p/d\n" % need)
                rows = crossing_verdict.read_crossing(path)
                self.assertEqual(rows, {("p/q", "p/d"): (300.0, "u_A", "u_B", "-")})

    def test_a_report_without_its_header_stops(self):
        # a file cut short to nothing, or rows without the header, is not a
        # report: read as one, it would have no pair over the budget
        with tempfile.TemporaryDirectory() as d:
            firm = write_crossing(d, "firm.txt", rows_of(moving(150, 201.4)))
            empty = os.path.join(d, "empty.txt")
            open(empty, "w").close()
            headless = os.path.join(d, "headless.txt")
            with open(headless, "w") as f:
                f.write("160.0 u_A u_B - p/q p/d\n")
            for final, why in [(empty, "the file is empty"), (headless, "first line")]:
                status, out, err = self.run_tool("--expect", "moved", 150, firm, final)
                self.assertEqual((status, out), (1, ""), final)
                self.assertIn("not crossing_report.py's crossing.txt", err)
                self.assertIn(why, err)

    def test_a_row_that_is_not_a_crossing_row_stops(self):
        with tempfile.TemporaryDirectory() as d:
            firm, final = self.passes(d, 150, moving(150, 201.4), [])[1:]
            with open(final, "a") as f:
                f.write("crossing 12\n")
            status, out, err = self.run_tool(150, firm, final)
            self.assertEqual(status, 1)
            self.assertIn("final.txt:2: not a crossing row: crossing 12", err)

    def test_sets_are_reported_not_a_condition(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 160.0, 50))
            same = write_sets(d, "a.txt", ["u_A u_B", "u_C"])
            reordered = write_sets(d, "b.txt", ["u_C", "u_B u_A"])
            other = write_sets(d, "c.txt", ["u_A u_B", "u_C", "u_D u_C"])
            status, out, err = self.run_tool("--sets", same, reordered, *args)
            self.assertEqual(status, 0)
            self.assertEqual(out.splitlines()[1], "sets: the same")
            status, out, err = self.run_tool(
                "--expect", "moved", "--sets", same, other, *args
            )
            self.assertEqual((status, err), (0, ""))
            self.assertEqual(out.splitlines()[1], "sets: differ (2 firm, 3 final)")
            self.assertTrue(out.startswith("moved the crossings: "), out)

    def test_the_paths_inside_one_macro_are_reported_not_a_condition(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 160.0, 50))
            firm_time = write_time(
                os.path.join(d, "firm"),
                [(180.0, "u_B"), (170.0, "u_B"), (160.0, "u_C"), (155.0, "u_D")],
            )
            final_time = write_time(
                os.path.join(d, "final"),
                [(190.0, "u_B"), (160.0, "u_C"), (120.0, "u_D"), (170.0, "u_E")],
            )
            status, out, err = self.run_tool("--time", firm_time, final_time, *args)
            self.assertEqual((status, err), (0, ""))
            self.assertIn("| u_B | 2 | 180.0 | 1 | 190.0 | 0 |", out)
            self.assertIn("| u_E | 0 | 0.0 | 1 | 170.0 | 1 |", out)
            # u_D's paths under the budget are not gone, only not over it
            self.assertEqual(out.splitlines()[-1], "none")

    def test_a_macro_whose_paths_are_gone_from_the_final_sets_is_listed(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 160.0, 50))
            firm_time = write_time(
                os.path.join(d, "firm"),
                [(180.0, "u_B"), (170.0, "u_B"), (160.0, "u_C"), (155.0, "u_D")],
            )
            # u_B has no row at all in the final sets, u_C has one under the
            # budget, u_D one over it
            final_time = write_time(
                os.path.join(d, "final"), [(120.0, "u_C"), (160.0, "u_D")]
            )
            status, out, err = self.run_tool("--time", firm_time, final_time, *args)
            self.assertEqual((status, err), (0, ""))
            lines = out.splitlines()
            at = [i for i, l in enumerate(lines) if l.startswith("macros whose paths")]
            self.assertEqual(len(at), 1, out)
            self.assertIn("(reported, not a condition)", lines[at[0]])
            self.assertEqual(
                lines[at[0] + 1 :],
                [
                    "| macro | firm rows | firm worst |",
                    "|---|---:|---:|",
                    "| u_B | 2 | 180.0 |",
                ],
            )

    def test_no_macro_gone_is_said(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 160.0, 50))
            both = write_time(os.path.join(d, "both"), [(180.0, "u_B")])
            status, out, err = self.run_tool("--time", both, both, *args)
            self.assertEqual((status, err), (0, ""))
            self.assertEqual(out.splitlines()[-1], "none")

    def test_a_time_directory_without_reports_stops(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 150, moving(150, 201.4), moving(150, 160.0, 50))
            some = write_time(os.path.join(d, "some"), [(180.0, "u_B")])
            empty = os.path.join(d, "empty")
            os.makedirs(empty)
            status, out, err = self.run_tool("--time", some, empty, *args)
            self.assertEqual(status, 1)
            self.assertIn("crossing_verdict: no cross.txt.<n> in %s" % empty, err)

    def test_no_budget_or_prediction_is_written_in(self):
        with tempfile.TemporaryDirectory() as d:
            args = self.passes(d, 1234, moving(1234, 1500.0), moving(1234, 1300.0, 50))
            status, out, err = self.run_tool(*args)
            self.assertEqual(status, 0)
            self.assertIn("over 1234 ps", out.splitlines()[0])
            self.assertNotIn("2,000", out)
            self.assertNotIn("2000", out)
            self.assertNotIn("prediction", out)


class WrapperTest(unittest.TestCase):
    """crossing_verdict.sh: the control first, a report against itself,
    then the verdict, whose output and exit status are the test's."""

    WRAPPER = os.path.join(
        os.path.dirname(os.path.abspath(crossing_verdict.__file__)),
        "crossing_verdict.sh",
    )

    def checker(self, d, name, body):
        path = os.path.join(d, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(path, 0o755)
        return path

    def run_wrapper(self, *args):
        done = subprocess.run(
            ["sh", self.WRAPPER] + [str(a) for a in args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        return done.returncode, done.stdout, done.stderr

    def reports(self, d, final_needs):
        firm = write_crossing(d, "firm.txt", rows_of(moving(150, 201.4)))
        final = write_crossing(d, "final.txt", rows_of(final_needs))
        return firm, final

    def test_a_checker_that_cannot_tell_a_report_from_itself_fails_the_control(self):
        with tempfile.TemporaryDirectory() as d:
            # it says moved whatever it is given, as a rule that cannot tell
            # the two passes apart would
            always = self.checker(
                d,
                "always_moved",
                'echo "moved the crossings: always"\n'
                '[ "$1 $2" = "--expect nothing" ] && exit 1\n'
                "exit 0\n",
            )
            firm, final = self.reports(d, moving(150, 160.0, 50))
            status, out, err = self.run_wrapper(always, 150, firm, final)
            self.assertEqual((status, out), (1, ""))
            self.assertIn(
                "the control failed: the first pass against itself must do nothing",
                err,
            )
            self.assertIn("moved the crossings: always", err)

    def test_the_verdict_follows_the_control(self):
        with tempfile.TemporaryDirectory() as d:
            tool = self.checker(
                d,
                "verdict",
                'exec "%s" "%s" "$@"\n'
                % (sys.executable, os.path.abspath(crossing_verdict.__file__)),
            )
            firm, final = self.reports(d, moving(150, 160.0, 50))
            status, out, err = self.run_wrapper(
                tool, 150, firm, final, "--expect", "moved"
            )
            self.assertEqual((status, err), (0, ""))
            self.assertTrue(out.startswith("moved the crossings: "), out)
            # the control passed; the verdict's own stop is the test's
            firm, final = self.reports(d, moving(150, 201.4))
            status, out, err = self.run_wrapper(
                tool, 150, firm, final, "--expect", "moved"
            )
            self.assertEqual(status, 1)
            self.assertNotIn("the control failed", err)
            self.assertIn(
                "expected the crossings moved, the verdict is DID NOTHING", err
            )


if __name__ == "__main__":
    unittest.main()
