"""crossing_floor_check.py on reports written here, in the format
crossing_floor.tcl writes."""

import contextlib
import io
import os
import tempfile
import unittest

import crossing_floor_check


def row(
    placed,
    floor,
    end="u_B/r/D",
    place="10.0 20.0",
    clock=("31.0", "31.0"),
    start="u_A/q/CLK",
    frm="u_A",
    to="u_B",
    through="-",
):
    return "\t".join(
        [placed, floor, clock[0], clock[1], frm, to, through, start, end, place]
    )


def report(rows, mode="floor"):
    return (
        "# crossing_floor mode=%s period_ps=1000 data_min_ps=100\n" % mode
        + "# placed_ps\tfloor_ps\tclock_placed_ps\tclock_floor_ps\tfrom_macro"
        "\tto_macro\tthrough_macros\tstartpoint\tendpoint\tend_x end_y\n"
        + "".join(r + "\n" for r in rows)
    )


# set 0: two ends over 150 ps as placed, one still over with no signal
# wire; one under the budget; set 1: a path through a third macro
FLOOR = {
    0: report(
        [
            row("190.8", "160.2"),
            row("170.0", "120.5", end="u_B/s/D", place="11.0 20.0"),
            row("130.0", "-", end="u_B/t/D", place="12.0 20.0"),
        ]
    ),
    1: report(
        [
            row(
                "180.0",
                "140.0",
                end="u_D/r/D",
                frm="u_A",
                to="u_D",
                through="u_C,u_E",
            ),
        ]
    ),
}


def control_of(sets):
    """The control's report: the first reading twice."""
    out = {}
    for n, text in sets.items():
        lines = []
        for line in text.splitlines():
            if line.startswith("# crossing_floor "):
                line = line.replace("mode=floor", "mode=control")
            elif not line.startswith("#"):
                f = line.split("\t")
                f[1] = f[0]
                f[3] = f[2]
                line = "\t".join(f)
            lines.append(line)
        out[n] = "\n".join(lines) + "\n"
    return out


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, sets):
        d = os.path.join(self.tmp.name, name)
        os.makedirs(d)
        for n, text in sets.items():
            with open(os.path.join(d, "cross.txt.%d" % n), "w") as f:
                f.write(text)
        return d

    def check(self, sets, budget=150.0, name="floor"):
        reports = crossing_floor_check.read_dir(self.write(name, sets))
        return crossing_floor_check.check(budget, reports)

    def main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = crossing_floor_check.main(argv)
        return code, out.getvalue()

    def test_floor_lower(self):
        lines, errors = self.check(FLOOR)
        self.assertEqual(errors, [])
        self.assertIn("3 ends over 150 ps as placed, worst 190.8 ps", lines[0])
        self.assertIn("1 still over with no signal wire, worst 160.2 ps", lines[0])
        # groups spelt as crossing_ends.py spells them
        self.assertIn("u_A>u_B\t2\t190.8\t1\t160.2", lines)
        self.assertIn("u_A>u_C>u_E>u_D\t1\t180.0\t0\t-", lines)
        self.assertIn(
            "clock: 4 rows compared, 1 of them with no crossing path over"
            " 100 ps in the second reading; the capture clock delay differs"
            " in 0",
            lines,
        )

    def test_not_lower(self):
        # the negative control: nothing taken away, the worst is the same
        sets = {0: report([row("190.8", "190.8"), row("170.0", "120.5", end="x")])}
        _, errors = self.check(sets)
        self.assertTrue(any("is not lower" in e for e in errors), errors)

    def test_second_reading_all_under_data_min(self):
        # wire is the whole story: no end has a crossing path over
        # data_min in the second reading, and crossing_floor.tcl writes
        # every end's capture clock delay in it all the same
        lines, errors = self.check(
            {
                0: report(
                    [
                        row("190.8", "-"),
                        row("170.0", "-", end="u_B/s/D", place="11.0 20.0"),
                    ]
                )
            }
        )
        self.assertEqual(errors, [])
        self.assertIn(
            "2 ends over 150 ps as placed, worst 190.8 ps; 0 still over with"
            " no signal wire, worst under 100 ps",
            lines[0],
        )
        self.assertIn(
            "clock: 2 rows compared, 2 of them with no crossing path over"
            " 100 ps in the second reading; the capture clock delay differs"
            " in 0",
            lines,
        )

    def test_an_end_without_its_second_clock_fails(self):
        # an end of the first reading with no capture clock delay in the
        # second: its clock is not compared, though another end's is
        _, errors = self.check(
            {
                0: report(
                    [
                        row("190.8", "160.2"),
                        row(
                            "170.0",
                            "-",
                            end="u_B/s/D",
                            place="11.0 20.0",
                            clock=("31.0", "-"),
                        ),
                    ]
                )
            }
        )
        self.assertTrue(
            any(
                "1 ends of the first reading without both readings' capture"
                " clock delay" in e
                and "u_B/s/D" in e
                for e in errors
            ),
            errors,
        )

    def test_a_clock_compared_nowhere_fails(self):
        lines, errors = self.check(
            {0: report([row("190.8", "-", clock=("31.0", "-"))])}
        )
        self.assertIn("worst under 100 ps", lines[0])
        self.assertTrue(
            any("the clock check compared no row" in e for e in errors), errors
        )
        self.assertTrue(
            any("without both readings' capture clock delay" in e for e in errors),
            errors,
        )

    def test_clock_changed(self):
        # with a path into the end in the second reading, and without one
        for floor in ("150.0", "-"):
            sets = {0: report([row("190.8", floor, clock=("31.0", "24.5"))])}
            _, errors = self.check(sets, name="floor" + floor)
            self.assertTrue(
                any(
                    "capture clock delay differs" in e and "u_B/r/D" in e
                    for e in errors
                ),
                errors,
            )

    def test_no_reports(self):
        _, errors = self.check({})
        self.assertTrue(any("no crossing_floor reports" in e for e in errors), errors)

    def test_no_ends(self):
        _, errors = self.check({0: report([])})
        self.assertTrue(any("nothing to measure" in e for e in errors), errors)

    def test_wrong_directory(self):
        _, errors = self.check(control_of(FLOOR))
        self.assertTrue(any("the wrong directory" in e for e in errors), errors)

    def test_end_in_two_sets(self):
        # one end, two sets: counted once, the worst reading of each kind
        sets = {
            0: report([row("190.8", "140.0")]),
            1: report([row("185.0", "155.0")]),
        }
        lines, errors = self.check(sets)
        self.assertEqual(errors, [])
        self.assertIn("u_A>u_B\t1\t190.8\t1\t155.0", lines)

    def test_name_and_place(self):
        # two registers with one report name are two ends
        sets = {
            0: report([row("190.8", "160.0"), row("180.0", "150.1", place="99.0 1.0")])
        }
        lines, _ = self.check(sets)
        self.assertIn("u_A>u_B\t2\t190.8\t2\t160.0", lines)

    def test_at_the_budget_is_not_over_it(self):
        # over the budget is needing more than it, as crossing_report.py,
        # crossing_ends.py and crossing_verdict.py count
        sets = {
            0: report([row("190.8", "150.0"), row("150.0", "120.0", end="u_B/s/D")])
        }
        lines, errors = self.check(sets)
        self.assertEqual(errors, [])
        self.assertIn("1 ends over 150 ps as placed", lines[0])
        self.assertIn("0 still over with no signal wire", lines[0])

    def test_bad_row(self):
        sets = {0: report(["190.8\t160.0\tu_A"])}
        with self.assertRaises(ValueError):
            self.check(sets)

    def test_with_control(self):
        code, out = self.main(
            [
                "150",
                self.write("floor", FLOOR),
                "--control",
                self.write("control", control_of(FLOOR)),
            ]
        )
        self.assertEqual(code, 0, out)
        self.assertIn("the two readings identical in every one", out)
        self.assertIn("control: the check fails on it, as it must", out)

    def test_control_differs(self):
        control = control_of(FLOOR)
        control[0] = control[0].replace("170.0\t170.0", "170.0\t169.0")
        code, out = self.main(
            [
                "150",
                self.write("floor", FLOOR),
                "--control",
                self.write("control", control),
            ]
        )
        self.assertEqual(code, 1, out)
        self.assertIn("the readings differ with the wires as placed", out)

    def test_control_is_a_floor(self):
        # the floor's directory given as the control: not the same twice,
        # and the check passes on it, so it cannot be the control
        code, out = self.main(
            [
                "150",
                self.write("floor", FLOOR),
                "--control",
                self.write("control", FLOOR),
            ]
        )
        self.assertEqual(code, 1, out)
        self.assertIn("the check does not fail on the control", out)
        self.assertIn("the wrong directory", out)

    def sets_file(self, n):
        path = os.path.join(self.tmp.name, "sets.txt")
        with open(path, "w") as f:
            f.write("# one set per line\n")
            for i in range(n):
                f.write("u_A u_B%d\n" % i)
        return path

    def test_every_set_has_its_report(self):
        floor = self.write("floor", FLOOR)
        control = self.write("control", control_of(FLOOR))
        code, out = self.main(
            ["150", floor, "--control", control, "--sets", self.sets_file(2)]
        )
        self.assertEqual(code, 0, out)
        # a third set with no report, in both directories
        code, out = self.main(
            ["150", floor, "--control", control, "--sets", self.sets_file(3)]
        )
        self.assertEqual(code, 1, out)
        self.assertIn("set 2 has no report (cross.txt.2) in %s" % floor, out)
        self.assertIn("set 2 has no report (cross.txt.2) in %s" % control, out)
        # a report of a set that is not there
        code, out = self.main(["150", floor, "--sets", self.sets_file(1)])
        self.assertEqual(code, 1, out)
        self.assertIn(
            "cross.txt.1 in %s is the report of none of the 1 sets" % floor, out
        )

    def test_an_option_without_its_value_is_refused(self):
        code, out = self.main(["150", self.write("floor", FLOOR), "--sets"])
        self.assertEqual(code, 2, out)

    def test_floor_is_the_control(self):
        # the control's readings given as the floor: it fails, for its reason
        control = self.write("control", control_of(FLOOR))
        code, out = self.main(["150", control, "--control", control])
        self.assertEqual(code, 1, out)
        self.assertIn("is not lower", out)


if __name__ == "__main__":
    unittest.main()
