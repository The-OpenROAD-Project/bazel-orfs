"""crossing_ledger_check.py on ledgers and top level paths written here:
the ledger holds the slowest path through a net, its clock taken out,
within the tolerance and no further; how far that is from the period
the net needs is said and not checked; a part's halves at zero, or its
ledger gone, fail the check, and for that."""

import contextlib
import io
import os
import tempfile
import unittest

import crossing_ledger_check

HEADER = "# part %s clock clock period 1000 clk_slew 10.0 skew - arcs_k 16\n"

# block A launches 100 ps into the hub, which captures in 50: 150
HUB = ["in u_A__q 50.0 20.0 -"]
A = ["out q 100.0 90.0 - - 0.0 -"]


def write(d, name, lines):
    path = os.path.join(d, name + ".txt")
    with open(path, "w") as f:
        f.write("".join(l + "\n" for l in lines))
    return path


def part(d, name, lines):
    return write(d, name, [(HEADER % name).rstrip()] + lines)


def path(net, free, clock=0.0):
    return "path %s %.2f %.2f %.2f u_A/r/CLK u_parent/s/D" % (
        net,
        free + clock,
        free,
        clock,
    )


class Check(unittest.TestCase):
    def run_check(self, top, hub=HUB, a=A, more=()):
        """The check's exit status, None when it passes, and what it said."""
        with tempfile.TemporaryDirectory() as d:
            argv = ["--top", write(d, "top", top), "--hub", part(d, "hub", hub)]
            if a is not None:
                argv += ["--block", "A=" + part(d, "A", a)]
            out = io.StringIO()
            status = None
            with contextlib.redirect_stdout(out):
                try:
                    crossing_ledger_check.main(argv + list(more))
                except SystemExit as e:
                    status = e.code
            return status, out.getvalue()

    def test_the_net_s_halves_sum_to_its_slowest_path(self):
        status, said = self.run_check([path("u_A__q", 150.0), path("u_A__q", 90.0)])
        self.assertIsNone(status, said)
        self.assertIn("1 nets, 2 paths", said)

    def test_within_the_larger_of_20_ps_and_a_tenth_of_the_path(self):
        for free in (131.0, 169.0):
            status, said = self.run_check([path("u_A__q", free)])
            self.assertIsNone(status, free)
        # a tenth of a long path: 1,000 + 500 against 1,600
        status, _ = self.run_check(
            [path("u_A__q", 1600.0)],
            hub=["in u_A__q 500.0 200.0 -"],
            a=["out q 1000.0 900.0 - - 0.0 -"],
        )
        self.assertIsNone(status)

    def test_a_path_longer_than_the_halves_fails(self):
        status, _ = self.run_check([path("u_A__q", 171.0)])
        self.assertIn("ledger under the top level: 1 paths through 1 nets", status)
        self.assertIn(
            "u_A__q 150.0 against 171.0 ps (u_A/r/CLK to u_parent/s/D)", status
        )

    def test_halves_longer_than_any_path_fail(self):
        status, _ = self.run_check([path("u_A__q", 129.0), path("u_A__q", 60.0)])
        self.assertIn("ledger over the top level: on 1 nets", status)
        self.assertIn("u_A__q 150.0 against 129.0 ps", status)

    def test_a_net_only_one_of_them_has_fails(self):
        status, _ = self.run_check([path("u_A__q", 150.0), path("u_A__other", 150.0)])
        self.assertIn("the ledger has no row for 1 nets", status)
        self.assertIn("u_A__other", status)
        status, _ = self.run_check(["none u_A__q"])
        self.assertIn("the top level times no path through 1 nets", status)

    def test_a_clock_the_ledger_does_not_hold_fails(self):
        status, said = self.run_check(
            [path("u_A__q", 150.0, clock=30.0)], more=["--max-skew", "40"]
        )
        self.assertIsNone(status, said)
        status, _ = self.run_check(
            [path("u_A__q", 150.0, clock=-41.0)], more=["--max-skew", "40"]
        )
        self.assertIn(
            "the top level's clock adds -41.0 ps to a path through u_A__q", status
        )

    def test_how_far_a_path_is_from_the_period_is_said_not_checked(self):
        # 150 ps of path, and 30 ps of clock on it at the top level: the
        # net needs 180, which the ledger is 30 under, and holds no part of
        status, said = self.run_check(
            [path("u_A__q", 150.0, clock=30.0)], more=["--max-skew", "40"]
        )
        self.assertIsNone(status, said)
        self.assertIn(
            "as a period, the top level's clock in, which no ledger holds: 1 of 1 "
            "nets outside the tolerance, 1 of them with the ledger under",
            said,
        )
        self.assertIn("worst u_A__q, 150.0 against 180.0 ps", said)
        status, said = self.run_check([path("u_A__q", 150.0, clock=10.0)])
        self.assertIn("0 of 1 nets outside the tolerance", said)

    def test_a_ledger_that_reads_under_on_average_is_warned_of(self):
        _, said = self.run_check([path("u_A__q", 165.0)])
        self.assertIn("WARNING: the ledger reads 15.0 ps under the top level", said)
        _, said = self.run_check([path("u_A__q", 155.0)])
        self.assertNotIn("WARNING", said)

    def test_a_part_s_halves_at_zero_fail_by_its_nets(self):
        for part_name in ("hub", "A"):
            status, _ = self.run_check(
                [path("u_A__q", 150.0)], more=["--zero", part_name]
            )
            self.assertIn("ledger under the top level", status)
            self.assertIn("u_A__q", status)

    def test_one_half_at_zero_fails_by_its_net(self):
        # two nets, the slower through u_A__r: its launch, 100 of its 150
        # ps, at zero, and the check fails on that net and no other
        status, said = self.run_check(
            [path("u_A__q", 140.0), path("u_A__r", 150.0)],
            hub=["in u_A__q 40.0 20.0 -", "in u_A__r 50.0 20.0 -"],
            a=["out q 100.0 90.0 - - 0.0 -", "out r 100.0 90.0 - - 0.0 -"],
            more=["--zero-half"],
        )
        self.assertIn("one half at zero: A's launch into u_A__r", said)
        self.assertIn("ledger under the top level: 1 paths through 1 nets", status)
        self.assertIn("u_A__r 50.0 against 150.0 ps", status)

    def test_a_block_s_ledger_gone_fails_by_its_name(self):
        status, _ = self.run_check([path("u_A__q", 150.0)], more=["--drop", "A"])
        self.assertIn("no ledger for block A", status)

    def test_zero_keeps_what_a_pin_does_not_have(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = part(
                d,
                "hub",
                [
                    "out u_B__d 90.0 80.0 - - 12.0 mcp",
                    "in u_A__q - - -",
                    "feed u_A__q 40.0 10.0",
                    "arc u_A__q u_B__d 40.0 10.0 complete",
                ],
            )
            crossing_ledger_check.zeroed(ledger, os.path.join(d, "zero.txt"))
            with open(os.path.join(d, "zero.txt")) as f:
                self.assertEqual(
                    f.read().splitlines()[1:],
                    [
                        "out u_B__d 0.00 0.00 - - 12.0 mcp",
                        "in u_A__q - - -",
                        "feed u_A__q 0.00 0.00",
                        "arc u_A__q u_B__d 0.00 0.00 complete",
                    ],
                )


class Same(unittest.TestCase):
    def same(self, a, b):
        with tempfile.TemporaryDirectory() as d:
            return crossing_ledger_check.same(part(d, "a", a), part(d, "b", b))[0]

    def test_two_readings_of_one_half_agree_within_a_tenth_of_a_ps(self):
        self.assertEqual(
            self.same(["in d 60.00 55.00 -"], ["in d 60.09 54.95 mcp"]), []
        )
        errors = self.same(["in d 60.00 55.00 -"], ["in d 60.00 55.20 -"])
        self.assertEqual(len(errors), 1)
        self.assertIn("in d", errors[0])

    def test_a_half_one_reading_lacks_differs(self):
        self.assertEqual(len(self.same(["in d 60.0 55.0 -"], ["in d - - -"])), 1)
        errors = self.same(
            ["in d 60.0 55.0 -", "arc d q 1.0 1.0 complete"], ["in d 60.0 55.0 -"]
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("arc d q", errors[0])
        # an input's slowest feed-through is a half like any other
        errors = self.same(
            ["in d - - -", "feed d 9.0 8.0"], ["in d - - -", "feed d 9.0 8.3"]
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("feed d", errors[0])


class Spot(unittest.TestCase):
    BOTH = [
        "# spot in d 3 min 10.00 max 30.00 half 30.00",
        "# spot out q 2 min 70.00 max 90.00 half 90.00",
    ]

    def spot(self, lines):
        with tempfile.TemporaryDirectory() as d:
            return crossing_ledger_check.spot(part(d, "hub", lines))

    def test_the_half_is_the_slowest_register_behind_the_pin(self):
        errors, lines = self.spot(self.BOTH)
        self.assertEqual(errors, [])
        self.assertEqual(len(lines), 2)

    def test_a_half_that_is_not_the_slowest_fails(self):
        errors, _ = self.spot(
            [self.BOTH[0], "# spot out q 2 min 70.00 max 90.00 half 70.00"]
        )
        self.assertTrue(
            any("out q: the ledger holds 70.00 ps" in e for e in errors), errors
        )

    def test_one_register_behind_every_pin_shows_nothing(self):
        errors, _ = self.spot(
            [self.BOTH[0], "# spot out q 1 min 90.00 max 90.00 half 90.00"]
        )
        self.assertTrue(any(e.startswith("no out pin checked") for e in errors), errors)


class Miss(unittest.TestCase):
    PINS = [
        "in a 310.00 100.00 -",
        "in b 290.00 100.00 -",
        "out q 500.00 400.00 120.00 90.00 0.0 -",
    ]

    def miss(self, lines):
        with tempfile.TemporaryDirectory() as d:
            return crossing_ledger_check.miss(part(d, "hub", lines + self.PINS))

    def test_the_count_is_the_halves_over_the_budget(self):
        errors, lines = self.miss(
            [
                "# miss in2reg 1/2 worst a 310.00 budget 300",
                "# miss reg2out 0/1 worst q 500.00 budget 600",
                "# miss in2out 1/1 worst q 120.00 budget 100",
            ]
        )
        self.assertEqual(errors, [])
        self.assertIn(
            "miss: 2 pins over their budgets, and the ledger was written", lines
        )

    def test_a_count_the_halves_do_not_give_fails(self):
        errors, _ = self.miss(["# miss in2reg 2/2 worst a 310.00 budget 300"])
        self.assertTrue(
            any("in2reg: the ledger counts 2 of 2" in e for e in errors), errors
        )

    def test_no_pin_over_shows_nothing(self):
        errors, _ = self.miss(["# miss reg2out 0/1 worst q 500.00 budget 600"])
        self.assertTrue(any("no pin is over" in e for e in errors), errors)
        errors, _ = self.miss(["# miss - no boundary budget given"])
        self.assertTrue(any("no boundary budget" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
