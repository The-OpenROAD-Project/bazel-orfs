"""crossing_ledger.py: a crossing net's path is its launch half plus its
capture half, the longest chain through any feed-throughs, the hub's
share apart from its partners'; a half that is missing stops the join
or is named, never read as zero; and a chain a feed-through cut from a
part's list may lengthen is never shown to fit."""

import os
import tempfile
import unittest

import crossing_ledger

HEADER = "# part %s clock clock period 1000 clk_slew 10.0 skew - arcs_k 16 feeds %d\n"


def part(d, name, lines):
    path = os.path.join(d, name + ".txt")
    feeds = sum(1 for l in lines if l.startswith("feed "))
    with open(path, "w") as f:
        f.write(HEADER % (name, feeds) + "".join(l + "\n" for l in lines))
    return path


def by_net(rows):
    return {r["net"]: r for r in rows}


class CrossingLedgerTest(unittest.TestCase):
    def join(self, d, hub, blocks, budget=2000.0, **more):
        return crossing_ledger.join(
            part(d, "hub", hub),
            {name: part(d, name, lines) for name, lines in blocks.items()},
            budget,
            **more
        )

    def test_a_net_s_path_is_its_launch_and_its_capture(self):
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
            self.assertAlmostEqual(rows["u_A__q"]["path"], 150.0)
            self.assertAlmostEqual(rows["u_A__q"]["path_zero"], 110.0)
            self.assertEqual(
                (rows["u_A__q"]["from"], rows["u_A__q"]["to"]), ("A", "hub")
            )
            # the hub launches, block A captures
            self.assertAlmostEqual(rows["u_A__d"]["path"], 100.0)
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
                self.assertAlmostEqual(r["path"], 200.0)
                self.assertAlmostEqual(r["path_zero"], 145.0)
                # the hub's wires at zero, A and B as routed
                self.assertAlmostEqual(r["path_hub_zero"], 170.0)
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
            self.assertAlmostEqual(by_net(rows)["u_B__d"]["path"], 115.0)

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
                "hub debt 100.0 ps: each net's ps over, summed over the nets, a "
                "chain through two nets twice",
                lines,
            )

    def test_the_top_level_s_clock_comes_off_the_budget(self):
        hub = ["in u_A__q 50.0 20.0 -"]
        blocks = {"A": ["out q 100.0 90.0 - - 0.0 -"]}
        with tempfile.TemporaryDirectory() as d:
            # 150 ps of path: within 200 ps, not within 200 less 60 of clock
            rows, lines, _ = self.join(d, hub, blocks, budget=200.0)
            self.assertEqual(rows[0]["class"], "ok")
            # a path is no period: said where no clock is allowed for
            self.assertTrue(any(l.startswith("no clock in any path") for l in lines))
            rows, lines, _ = self.join(d, hub, blocks, budget=200.0, clock=60.0)
            self.assertEqual(rows[0]["class"], "closable-by-hub-placement")
            self.assertAlmostEqual(rows[0]["allowance"], 40.0)
            self.assertIn("crossing ledger: 1 nets, 1 over 140 ps", lines)
            self.assertFalse(any(l.startswith("no clock in any path") for l in lines))

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
            # unless the port is said to be the design's own
            _, lines, _ = self.join(d, ["in u_A__q 50.0 20.0 -"], {}, own=["A"])
            self.assertIn("own 1 hub ports of the design's own", lines)
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
                    "feed u_A__q 40.0 10.0",
                    "arc u_A__q u_B__d 40.0 10.0 truncated",
                ],
                {
                    # a launch behind q is under a multicycle exception
                    "A": ["out q 100.0 80.0 - - 0.0 mcp"],
                    "B": ["in d 60.0 55.0 -"],
                },
            )
            rows = by_net(rows)
            # a feed-through cut from the list may end at u_B__d
            self.assertIn("truncated", rows["u_B__d"]["flags"])
            self.assertEqual(rows["u_B__d"]["class"], "unknown")
            # none starts at u_A__q that its one output does not list
            self.assertNotIn("truncated", rows["u_A__q"]["flags"])
            self.assertEqual(rows["u_A__q"]["class"], "ok")
            self.assertIn("mcp", rows["u_B__d"]["flags"])
            self.assertIn("truncated 1 nets, which may read low: u_B__d", lines)
            self.assertTrue(any(l.startswith("mcp 2 nets") for l in lines))

    # Hub outputs u_B__d and u_C__e, their lists cut at the one worst
    # feed-through: r > u_B__d (400) and s > u_C__e (20). q's slowest
    # feed-through is 390, to u_B__d, and not listed: 900 + 390 + 50.
    CUT_HUB = [
        "in u_A__r - - -",
        "in u_A__s - - -",
        "out u_B__d - - 400.0 400.0 - -",
        "out u_C__e - - 20.0 20.0 - -",
        "feed u_A__q 390.0 390.0",
        "feed u_A__r 400.0 400.0",
        "feed u_A__s 20.0 20.0",
        "arc u_A__r u_B__d 400.0 400.0 truncated",
        "arc u_A__s u_C__e 20.0 20.0 truncated",
    ]
    CUT_BLOCKS = {
        "A": [
            "out q 900.0 900.0 - - 0.0 -",
            "out r 100.0 100.0 - - 0.0 -",
            "out s 100.0 100.0 - - 0.0 -",
        ],
        "B": ["in d 50.0 50.0 -"],
        "C": ["in e 50.0 50.0 -"],
    }

    def test_a_feed_through_cut_from_the_list_is_not_read_as_absent(self):
        with tempfile.TemporaryDirectory() as d:
            rows, lines, blind = self.join(
                d, ["in u_A__q - - -"] + self.CUT_HUB, self.CUT_BLOCKS, budget=1000.0
            )
            # the hub captures nothing behind q, and the net is not one
            # that is launched and never captured: it has no row, by name
            self.assertNotIn("u_A__q", by_net(rows))
            self.assertEqual(blind, ["u_A__q"])
            self.assertIn("no-capture 0 nets", lines)
            self.assertIn(
                "cut 1 nets, launched or captured, if at all, through a "
                "feed-through cut from its part's list: u_A__q",
                lines,
            )
            # and no net the 1,340 ps may run through is shown to fit
            rows = by_net(rows)
            self.assertAlmostEqual(rows["u_B__d"]["path"], 550.0)
            self.assertEqual(rows["u_B__d"]["class"], "unknown")
            self.assertEqual(rows["u_C__e"]["class"], "unknown")

    def test_a_capture_does_not_hide_a_feed_through_cut_from_the_list(self):
        with tempfile.TemporaryDirectory() as d:
            rows, lines, blind = self.join(
                d,
                ["in u_A__q 60.0 60.0 -"] + self.CUT_HUB,
                self.CUT_BLOCKS,
                budget=1000.0,
            )
            rows = by_net(rows)
            # the hub's own capture, 900 + 60: a lower bound, and said so
            self.assertAlmostEqual(rows["u_A__q"]["path"], 960.0)
            self.assertIn("truncated", rows["u_A__q"]["flags"])
            self.assertEqual(rows["u_A__q"]["class"], "unknown")
            self.assertEqual(blind, [])
            self.assertIn("crossing ledger: 5 nets, 0 over 1000 ps", lines)
            self.assertIn("class ok 2", lines)
            self.assertIn("class unknown 3", lines)

    def test_a_feed_through_cut_from_the_list_that_cannot_matter_is_no_flag(self):
        with tempfile.TemporaryDirectory() as d:
            # behind q a capture slower than any feed-through q has, 390,
            # and what follows the outputs it may end at, 50
            rows, _, _ = self.join(
                d, ["in u_A__q 440.0 440.0 -"] + self.CUT_HUB, self.CUT_BLOCKS
            )
            rows = by_net(rows)
            self.assertAlmostEqual(rows["u_A__q"]["path"], 1340.0)
            self.assertEqual(rows["u_A__q"]["flags"], [])
            # r and s feed through to outputs that list them: nothing of
            # theirs was cut
            self.assertEqual(rows["u_A__r"]["flags"], [])
            self.assertEqual(rows["u_A__s"]["flags"], [])

    def test_a_loop_only_a_cut_feed_through_would_close_is_a_flag(self):
        with tempfile.TemporaryDirectory() as d:
            rows, _, _ = self.join(
                d,
                [
                    # q's feed-through, if it ends at u_A__d, where the list
                    # was cut, closes a loop through A; nobody knows
                    "in u_A__q 10.0 10.0 -",
                    "in u_B__z - - -",
                    "out u_A__d - - 7.0 7.0 - -",
                    "feed u_A__q 5.0 5.0",
                    "feed u_B__z 7.0 7.0",
                    "arc u_B__z u_A__d 7.0 7.0 truncated",
                ],
                {
                    "A": [
                        "in d - - -",
                        "out q 20.0 20.0 3.0 3.0 - -",
                        "feed d 3.0 3.0",
                        "arc d q 3.0 3.0 complete",
                    ],
                    "B": ["out z 40.0 40.0 - - 0.0 -"],
                },
            )
            rows = by_net(rows)
            # as listed: 40 + 7 + 3 + 10
            self.assertAlmostEqual(rows["u_A__q"]["path"], 60.0)
            for net in ("u_A__q", "u_A__d", "u_B__z"):
                self.assertIn("truncated", rows[net]["flags"], net)

    def test_a_cut_list_without_the_inputs_feeds_stops_the_join(self):
        with tempfile.TemporaryDirectory() as d:
            hub = os.path.join(d, "hub.txt")
            with open(hub, "w") as f:
                f.write(
                    "# part hub clock clock period 1000 clk_slew 10.0 skew - "
                    "arcs_k 1\n"
                    "in u_A__q - - -\n"
                    "out u_B__d - - 40.0 10.0 - -\n"
                    "arc u_A__q u_B__d 40.0 10.0 truncated\n"
                )
            with self.assertRaises(crossing_ledger.LedgerError) as e:
                crossing_ledger.join(hub, {}, 2000.0)
            self.assertIn("no `feeds` in its header", str(e.exception))
            # and a ledger with fewer feed lines than it says it wrote
            with open(hub, "w") as f:
                f.write((HEADER % ("hub", 1)) + "in u_A__q - - -\n")
            with self.assertRaises(crossing_ledger.LedgerError) as e:
                crossing_ledger.join(hub, {}, 2000.0)
            self.assertIn("has 0 feed lines, its header says 1", str(e.exception))

    def test_a_chain_through_the_hub_twice(self):
        with tempfile.TemporaryDirectory() as d:
            rows, _, _ = self.join(
                d,
                [
                    # the hub launches into B, B feeds it back, the hub
                    # feeds it on to C
                    "out u_B__d 100.0 80.0 - - 0.0 -",
                    "in u_B__q - - -",
                    "out u_C__e - - 300.0 250.0 - -",
                    "feed u_B__q 300.0 250.0",
                    "arc u_B__q u_C__e 300.0 250.0 complete",
                ],
                {
                    "B": [
                        "in d - - -",
                        "out q - - 200.0 190.0 - -",
                        "feed d 200.0 190.0",
                        "arc d q 200.0 190.0 complete",
                    ],
                    "C": ["in e 50.0 45.0 -"],
                },
            )
            rows = by_net(rows)
            for net in ("u_B__d", "u_B__q", "u_C__e"):
                r = rows[net]
                # 100 + 200 + 300 + 50, the one chain through all three
                self.assertAlmostEqual(r["path"], 650.0)
                self.assertAlmostEqual(r["path_zero"], 565.0)
                self.assertAlmostEqual(r["path_hub_zero"], 580.0)
                self.assertAlmostEqual(r["hub"], 400.0)
                self.assertAlmostEqual(r["partner"], 250.0)
                self.assertEqual(r["chain"], ["hub", "B", "hub", "C"])
                self.assertEqual(r["flags"], [])

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
