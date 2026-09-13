#!/usr/bin/env python3

"""Tests for select_designs.py.

The selection code makes two claims that the study leans on hard: that
greedy can get started when more than one witness is required, and that
"detected" means what the report says it means. Both are cheap to pin
down on synthetic events, which is the only place the ground truth is
known.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import select_designs as sel


def event(*designs):
    return {"commit": "x", "when": 0, "moved": set(designs)}


class Detection(unittest.TestCase):
    EVENTS = [
        event("a", "b", "c"),
        event("a", "d"),
        event("c", "d", "e"),
    ]

    def test_one_witness_is_any_overlap(self):
        self.assertEqual(sel.detected(self.EVENTS, {"a"}, 1), {0, 1})

    def test_two_witnesses_need_two_movers_in_the_same_event(self):
        self.assertEqual(sel.detected(self.EVENTS, {"a", "b"}, 2), {0})
        self.assertEqual(sel.detected(self.EVENTS, {"a", "d"}, 2), {1})

    def test_a_single_design_detects_nothing_at_two_witnesses(self):
        for d in "abcde":
            self.assertEqual(sel.detected(self.EVENTS, {d}, 2), set())


class GreedyBootstrap(unittest.TestCase):
    """Greedy must not stall when the first pick can detect nothing."""

    EVENTS = [event("a", "b"), event("a", "b"), event("c", "d")]

    def test_greedy_gets_past_the_first_pick(self):
        chosen, trail = sel.greedy(self.EVENTS, list("abcd"), 2, None, limit=4)
        self.assertTrue(trail, "greedy stalled before adding anything")
        self.assertGreaterEqual(len(chosen), 2)

    def test_greedy_finds_the_pair_that_covers_the_most(self):
        chosen, trail = sel.greedy(self.EVENTS, list("abcd"), 2, None, limit=2)
        self.assertEqual(chosen, {"a", "b"})
        self.assertEqual(trail[-1]["detected"], 2)

    def test_witness_score_is_capped_and_monotone(self):
        prev = -1
        for n in range(1, 5):
            score = sel.witness_score(self.EVENTS, set("abcd"[:n]), 2)
            self.assertGreaterEqual(score, prev)
            prev = score
        # Capped: adding every design cannot exceed witnesses per event.
        self.assertEqual(sel.witness_score(self.EVENTS, set("abcd"), 2), 2 * 3)

    def test_limit_is_respected(self):
        chosen, _ = sel.greedy(self.EVENTS, list("abcd"), 1, None, limit=2)
        self.assertEqual(len(chosen), 2)


class Cost(unittest.TestCase):
    def test_cost_is_superlinear_in_instances(self):
        # Ten times the instances must cost more than ten times as much,
        # or the proxy would understate what a big design takes.
        self.assertGreater(sel.cost_of(100000), 10 * sel.cost_of(10000))

    def test_cost_is_monotone(self):
        self.assertLess(sel.cost_of(500), sel.cost_of(5000))

    def test_zero_instances_does_not_explode(self):
        self.assertEqual(sel.cost_of(0), 1.0)


if __name__ == "__main__":
    unittest.main()
