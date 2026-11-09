"""crossing_ledger.py: a crossing net needs its launch half plus its
capture half, the longest chain through any feed-throughs, the hub's
share apart from its partners', and a half that is missing stops the
join or is named, never read as zero."""

import os
import tempfile
import unittest

import crossing_ledger

HEADER = "# part %s clock clock period 1000 clk_slew 10.0 skew - arcs_k 16\n"


def part(d, name, lines):
    path = os.path.join(d, name + ".txt")
    with open(path, "w") as f:
        f.write(HEADER % name + "".join(l + "\n" for l in lines))
    return path


def by_net(rows):
    return {r["net"]: r for r in rows}


class CrossingLedgerTest(unittest.TestCase):
    def join(self, d, hub, blocks, budget=2000.0):
        return crossing_ledger.join(
            part(d, "hub", hub),
            {name: part(d, name, lines) for name, lines in blocks.items()},
            budget,
        )

    def test_a_net_needs_its_launch_and_its_capture(self):
        with tempfile.TemporaryDirectory() as d:
            rows, _, _ = self.join(
                d,
                ["in u_A__q 50.0 20.0 -", "out u_A__d 70.0 40.0 - - 0.0 -"],
                {
                    "A": [
                        "out q 100.0 90.0 - - 0.0 -",
                        "in d 30.0 25.0 -",
                    ]
                },
            )
            rows = by_net(rows)
            # block A launches, the hub captures
            self.assertAlmostEqual(rows["u_A__q"]["need"], 150.0)
            self.assertAlmostEqual(rows["u_A__q"]["need_zero"], 110.0)
            self.assertEqual(
                (rows["u_A__q"]["from"], rows["u_A__q"]["to"]), ("A", "hub")
            )
            # the hub launches, block A captures
            self.assertAlmostEqual(rows["u_A__d"]["need"], 100.0)
            self.assertEqual(
                (rows["u_A__d"]["from"], rows["u_A__d"]["to"]), ("hub", "A")
            )

    def test_a_feed_through_chain_is_summed_over_every_part_on_it(self):
        with tempfile.TemporaryDirectory() as d:
            rows, _, _ = self.join(
                d,
                [
                    # the hub captures A's q itself, and feeds it through to B
                    "in u_A__q 30.0 20.0 -",
                    "out u_B__d - - 40.0 10.0 - -",
                    "arc u_A__q u_B__d 40.0 10.0 complete",
                ],
                {
                    "A": ["out q 100.0 80.0 - - 0.0 -"],
                    "B": ["in d 60.0 55.0 -"],
                },
                budget=180.0,
            )
            rows = by_net(rows)
            for net in ("u_A__q", "u_B__d"):
                r = rows[net]
                # 100 + 40 + 60, not the hub's own capture's 100 + 30
                self.assertAlmostEqual(r["need"], 200.0)
                self.assertAlmostEqual(r["need_zero"], 145.0)
                # the hub's wires at zero, A and B as routed
                self.assertAlmostEqual(r["need_hub_zero"], 170.0)
                self.assertAlmostEqual(r["hub"], 40.0)
                self.assertAlmostEqual(r["hub_zero"], 10.0)
                self.assertAlmostEqual(r["partner"], 160.0)
                self.assertAlmostEqual(r["allowance"], 20.0)
                self.assertEqual(r["class"], "closable-by-hub-placement")
                self.assertEqual(r["chain"], ["A", "hub", "B"])

    def test_the_slowest_launch_behind_a_pin_wins(self):
        with tempfile.TemporaryDirectory() as d:
            rows, _, _ = self.join(
                d,
                [
                    "in u_A__q - - -",
                    # the hub's own register behind the pin: 90; block A's,
                    # fed through: 100 + 5
                    "out u_B__d 90.0 90.0 5.0 5.0 0.0 -",
                    "arc u_A__q u_B__d 5.0 5.0 complete",
                ],
                {
                    "A": ["out q 100.0 100.0 - - 0.0 -"],
                    "B": ["in d 10.0 10.0 -"],
                },
            )
            self.assertAlmostEqual(by_net(rows)["u_B__d"]["need"], 115.0)

    def test_classes(self):
        with tempfile.TemporaryDirectory() as d:
            rows, lines, _ = self.join(
                d,
                [
                    "in u_A__ok 50.0 20.0 -",
                    "in u_A__place 150.0 20.0 -",
                    "in u_A__stuck 150.0 120.0 -",
                ],
                {
                    "A": [
                        "out ok 100.0 90.0 - - 0.0 -",
                        "out place 100.0 90.0 - - 0.0 -",
                        "out stuck 100.0 90.0 - - 0.0 -",
                    ]
                },
                budget=200.0,
            )
            rows = by_net(rows)
            self.assertEqual(rows["u_A__ok"]["class"], "ok")
            self.assertEqual(rows["u_A__place"]["class"], "closable-by-hub-placement")
            self.assertEqual(rows["u_A__stuck"]["class"], "not-closable-by-hub")
            self.assertIn("crossing ledger: 3 nets, 2 over 200 ps", lines)
            # 250 - 200, twice
            self.assertIn(
                "hub debt 100.0 ps: each net's ps over the budget, summed over the nets",
                lines,
            )

    def test_a_missing_pin_stops_the_join_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(crossing_ledger.LedgerError) as e:
                self.join(d, ["in u_A__q 50.0 20.0 -"], {"A": []})
            self.assertIn("hub port u_A__q: A's ledger has no pin q", str(e.exception))

    def test_a_missing_part_stops_the_join_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(crossing_ledger.LedgerError) as e:
                self.join(d, ["in u_A__q 50.0 20.0 -"], {})
            self.assertIn("no ledger for block A", str(e.exception))
            with self.assertRaises(crossing_ledger.LedgerError) as e:
                crossing_ledger.join(
                    part(d, "hub", []), {"A": os.path.join(d, "gone.txt")}, 2000.0
                )
            self.assertIn("A: no ledger", str(e.exception))

    def test_a_half_that_is_not_there_is_named_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            rows, lines, no_capture = self.join(
                d,
                [
                    # launched by A, captured by nothing in the hub
                    "in u_A__q - - -",
                    # launched by nothing
                    "out u_A__d - - - - - -",
                ],
                {
                    "A": [
                        "out q 100.0 90.0 - - 0.0 -",
                        "in d 30.0 25.0 -",
                    ]
                },
            )
            self.assertEqual(rows, [])
            self.assertEqual(no_capture, ["u_A__q"])
            self.assertIn(
                "no-capture 1 nets, launched and never captured: u_A__q", lines
            )
            self.assertIn("no-launcher 1 nets: nothing launches into them", lines)

    def test_a_half_routed_only_stops_the_join(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(crossing_ledger.LedgerError):
                self.join(d, ["in u_A__q 50.0 - -"], {"A": ["out q 1.0 1.0 - - 0.0 -"]})

    def test_a_loop_of_feed_throughs_stops_the_join(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(crossing_ledger.LedgerError) as e:
                self.join(
                    d,
                    [
                        "in u_A__q - - -",
                        "out u_A__d - - 1.0 1.0 - -",
                        "arc u_A__q u_A__d 1.0 1.0 complete",
                    ],
                    {
                        "A": [
                            "out q - - 1.0 1.0 - -",
                            "in d - - -",
                            "arc d q 1.0 1.0 complete",
                        ]
                    },
                )
            self.assertIn("a loop of feed-throughs", str(e.exception))

    def test_what_a_half_could_not_see_is_flagged_on_its_nets(self):
        with tempfile.TemporaryDirectory() as d:
            rows, lines, _ = self.join(
                d,
                [
                    "in u_A__q - - -",
                    "out u_B__d - - 40.0 10.0 - -",
                    "arc u_A__q u_B__d 40.0 10.0 truncated",
                ],
                {
                    # a launch behind q is under a multicycle exception
                    "A": ["out q 100.0 80.0 - - 0.0 mcp"],
                    "B": ["in d 60.0 55.0 -"],
                },
            )
            rows = by_net(rows)
            self.assertIn("truncated", rows["u_B__d"]["flags"])
            self.assertIn("truncated", rows["u_A__q"]["flags"])
            self.assertIn("mcp", rows["u_B__d"]["flags"])
            self.assertTrue(any(l.startswith("truncated 2 nets") for l in lines))
            self.assertTrue(any(l.startswith("mcp 2 nets") for l in lines))

    def test_the_design_s_own_ports_and_open_pins_are_counted(self):
        with tempfile.TemporaryDirectory() as d:
            _, lines, _ = self.join(
                d,
                ["in seed 50.0 20.0 -", "in u_A__q 50.0 20.0 -"],
                {"A": ["out q 100.0 90.0 - - 0.0 -", "out spare 1.0 1.0 - - 0.0 -"]},
            )
            self.assertIn("own 1 hub ports of the design's own", lines)
            self.assertIn("open 1 block pins the hub has no port for: A/spare", lines)

    def test_writes_the_rows_worst_first(self):
        with tempfile.TemporaryDirectory() as d:
            rows, lines, _ = self.join(
                d,
                ["in u_A__q 50.0 20.0 -", "in u_A__r 80.0 20.0 -"],
                {"A": ["out q 100.0 90.0 - - 0.0 -", "out r 100.0 90.0 - - 0.0 -"]},
            )
            out = os.path.join(d, "out")
            crossing_ledger.write(out, rows, lines, 2000.0)
            with open(os.path.join(out, "crossings.txt")) as f:
                body = [l.split() for l in f if not l.startswith("#")]
            self.assertEqual([r[0] for r in body], ["u_A__r", "u_A__q"])
            self.assertEqual(body[0][3], "180.0")
            self.assertEqual(len(body[0]), len(crossing_ledger.COLUMNS.split()))


if __name__ == "__main__":
    unittest.main()
