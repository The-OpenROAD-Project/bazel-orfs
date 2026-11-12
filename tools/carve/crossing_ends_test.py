"""crossing_ends.py: the second pass takes over exactly the end pins of the
first pass's crossing paths over the budget, each once, in the group of its
worst path."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

import crossing_ends

# crossing_paths.tcl's crossing_data.<n>.tsv, as it writes it
HEADER = (
    "# crossing paths over 100 ps at global route; period 1000 ps\n"
    "# need_ps\twire_ps\tfrom_macro\tto_macro\tthrough_macros\tstartpoint\t"
    "endpoint\tstart_x start_y\tend_x end_y\n"
)


def row(need, frm, to, through, start, end, start_at="1.0 2.0", end_at="3.0 4.0"):
    return "\t".join(
        [str(need), "12.5", frm, to, through, start, end, start_at, end_at]
    )


def write(d, name, rows, header=HEADER):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(header + "".join(r + "\n" for r in rows))
    return path


def lines(path):
    with open(path) as f:
        return f.read().splitlines()


class CrossingEndsTest(unittest.TestCase):
    def run_ends(self, d, budget=150):
        """The two files crossing_ends writes, as lists of their lines."""
        out = os.path.join(d, "out")
        with contextlib.redirect_stdout(io.StringIO()):
            status = crossing_ends.main(["crossing_ends", d, str(budget), out])
        self.assertEqual(status, 0)
        return (
            lines(os.path.join(out, "ends.tsv")),
            lines(os.path.join(out, "starts.txt")),
        )

    def stops(self, d, budget, why):
        """The tool exits non-zero with one line, for the reason the test is
        about, and writes nothing."""
        out = os.path.join(d, "out")
        done = subprocess.run(
            [sys.executable, crossing_ends.__file__, d, str(budget), out],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertIn(why, done.stderr)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1, done.stderr)
        self.assertFalse(os.path.exists(out))

    def test_through_macros_are_split_on_commas(self):
        # crossing_paths.tcl joins the macros a path passes through with
        # commas: two of them are two parts of the group, none is "-"
        with tempfile.TemporaryDirectory() as d:
            write(
                d,
                "crossing_data.0.tsv",
                [
                    row(200.0, "u_A", "u_D", "u_B,u_C", "a/q", "d/d"),
                    row(190.0, "u_A", "u_C", "u_B", "a/q", "c/d"),
                    row(180.0, "u_A", "u_B", "-", "a/q", "b/d"),
                ],
            )
            ends, _ = self.run_ends(d)
            groups = {line.split("\t")[1]: line.split("\t")[0] for line in ends}
            self.assertEqual(groups["d/d"], "u_A>u_B>u_C>u_D")
            self.assertEqual(groups["c/d"], "u_A>u_B>u_C")
            self.assertEqual(groups["b/d"], "u_A>u_B")
            # split on blanks, the macros would stay one name
            self.assertNotIn("u_A>u_B,u_C>u_D", groups.values())

    def test_a_pin_is_its_name_and_its_place(self):
        # a report names a register by its first and last level of
        # instances: two registers can share a name, and are two pins
        with tempfile.TemporaryDirectory() as d:
            write(
                d,
                "crossing_data.0.tsv",
                [
                    row(200.0, "u_A", "u_B", "-", "a/r", "b/r", "1 1", "9 9"),
                    row(190.0, "u_A", "u_B", "-", "a/r", "b/r", "2 2", "8 8"),
                ],
            )
            ends, starts = self.run_ends(d)
            self.assertEqual(
                ends, ["u_A>u_B\tb/r\t8 8", "u_A>u_B\tb/r\t9 9"], "keyed by name alone"
            )
            self.assertEqual(starts, ["a/r\t1 1", "a/r\t2 2"])

    def test_an_end_is_in_the_group_of_its_worst_path(self):
        with tempfile.TemporaryDirectory() as d:
            write(
                d,
                "crossing_data.0.tsv",
                [
                    row(180.0, "u_A", "u_C", "-", "a/q", "c/d"),
                    row(220.0, "u_B", "u_C", "-", "b/q", "c/d"),
                    row(200.0, "u_B", "u_C", "u_A", "b/q2", "c/d"),
                ],
            )
            ends, starts = self.run_ends(d)
            self.assertEqual(ends, ["u_B>u_C\tc/d\t3.0 4.0"])
            # the start pins are those of the worst paths only
            self.assertEqual(starts, ["b/q\t1.0 2.0"])

    def test_paths_of_every_file_count(self):
        with tempfile.TemporaryDirectory() as d:
            write(
                d,
                "crossing_data.0.tsv",
                [row(180.0, "u_A", "u_C", "-", "a/q", "c/d")],
            )
            write(
                d,
                "crossing_data.1.tsv",
                [row(210.0, "u_B", "u_C", "-", "b/q", "c/d")],
            )
            write(d, "cross.txt.0", ["not read"], header="")
            ends, _ = self.run_ends(d)
            self.assertEqual(ends, ["u_B>u_C\tc/d\t3.0 4.0"])

    def test_the_budget_itself_is_not_over_it(self):
        with tempfile.TemporaryDirectory() as d:
            write(
                d,
                "crossing_data.0.tsv",
                [
                    row(150.0, "u_A", "u_B", "-", "a/q", "b/at"),
                    row(150.1, "u_A", "u_B", "-", "a/q", "b/over"),
                    row(120.0, "u_A", "u_B", "-", "a/q", "b/under"),
                ],
            )
            ends, _ = self.run_ends(d, budget=150)
            self.assertEqual(ends, ["u_A>u_B\tb/over\t3.0 4.0"])

    def test_the_output_does_not_depend_on_the_order_of_the_rows(self):
        rows = [
            row(200.0, "u_B", "u_C", "-", "b/q", "c/d1"),
            row(200.0, "u_A", "u_C", "-", "a/q", "c/d1"),
            row(200.0, "u_A", "u_C", "-", "a/q0", "c/d1"),
            row(170.0, "u_A", "u_D", "-", "a/q", "d/d"),
            row(170.0, "u_A", "u_B", "u_C", "a/q", "b/d"),
        ]
        results = []
        for order in (rows, rows[::-1], rows[2:] + rows[:2]):
            with tempfile.TemporaryDirectory() as d:
                write(d, "crossing_data.0.tsv", order)
                results.append(self.run_ends(d))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])
        ends, starts = results[0]
        names = [line.split("\t")[1] for line in ends]
        self.assertEqual(names, sorted(names))
        # an equal need goes to the smaller group, then the smaller start
        self.assertIn("u_A>u_C\tc/d1\t3.0 4.0", ends)
        self.assertEqual(starts, sorted(set(starts)))
        self.assertIn("a/q\t1.0 2.0", starts)
        self.assertNotIn("a/q0\t1.0 2.0", starts)

    def test_no_crossing_data(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "cross.txt.0", ["200.0 crossing u_A u_B a/q b/d - 0"], header="")
            self.stops(d, 150, "no crossing_data.<n>.tsv in %s" % d)

    def test_no_end_over_the_budget(self):
        with tempfile.TemporaryDirectory() as d:
            write(
                d,
                "crossing_data.0.tsv",
                [row(150.0, "u_A", "u_B", "-", "a/q", "b/d")],
            )
            self.stops(
                d,
                150,
                "no crossing over 150 ps: nothing to unfirm; the firm Top is the "
                "result",
            )

    def test_a_data_file_without_rows_is_no_end_over_the_budget(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "crossing_data.0.tsv", [])
            self.stops(d, 150, "no crossing over 150 ps")

    def test_a_row_cut_short_stops_with_its_place(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "crossing_data.0.tsv", ["200.0\t1.0\tu_A\tu_B\t-\ta/q"])
            self.stops(d, 150, "crossing_data.0.tsv:3: 6 tab-separated columns, not 9")


if __name__ == "__main__":
    unittest.main()
