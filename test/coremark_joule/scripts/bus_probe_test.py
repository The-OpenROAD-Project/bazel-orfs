#!/usr/bin/env python3
"""Unit tests for the external-bus traffic differential."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bus_probe import per_iteration, read_probe, summarise  # noqa: E402


def write(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".busprobe", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


class ReadProbeTest(unittest.TestCase):
    def test_counters_are_read_by_name(self):
        self.assertEqual(
            {"ifu_xacts": 2788, "lsu_xacts": 934},
            read_probe(write("ifu_xacts 2788\nlsu_xacts 934\n")),
        )

    def test_a_malformed_line_is_an_error(self):
        with self.assertRaises(ValueError):
            read_probe(write("ifu_xacts 2788 extra\n"))

    def test_an_empty_probe_is_an_error(self):
        """A run that wrote nothing is a failed probe, not zero traffic."""
        with self.assertRaises(ValueError):
            read_probe(write("\n"))


class PerIterationTest(unittest.TestCase):
    def test_the_difference_is_one_iteration(self):
        self.assertEqual(
            {"ifu_xacts": 12},
            per_iteration({"ifu_xacts": 100}, {"ifu_xacts": 112}),
        )

    def test_mismatched_counters_are_an_error(self):
        with self.assertRaises(ValueError):
            per_iteration({"ifu_xacts": 1}, {"lsu_xacts": 1})

    def test_a_counter_going_backwards_is_an_error(self):
        """They are free-running and monotonic; this is a mismatched pair."""
        with self.assertRaises(ValueError):
            per_iteration({"ifu_xacts": 10}, {"ifu_xacts": 9})


class SummariseTest(unittest.TestCase):
    MEASURED = ({"ifu_xacts": 2788, "lsu_xacts": 934},
                {"ifu_xacts": 2788, "lsu_xacts": 934})

    def test_an_unchanged_bus_means_the_iteration_is_resident(self):
        result = summarise(*self.MEASURED)
        self.assertTrue(result["resident"])
        self.assertEqual(0, result["transfers_per_iteration"]["ifu_xacts"])

    def test_boot_traffic_is_carried_rather_than_discarded(self):
        """Zero steady-state traffic and a bus that never worked look the
        same in the delta; the boot counts tell them apart."""
        result = summarise(*self.MEASURED)
        self.assertEqual(2788, result["boot_transfers"]["ifu_xacts"])

    def test_any_traffic_at_all_means_not_resident(self):
        result = summarise({"ifu_xacts": 100}, {"ifu_xacts": 101})
        self.assertFalse(result["resident"])
        self.assertEqual(8, result["bytes_per_iteration"]["ifu_xacts"])

    def test_cycles_give_a_rate(self):
        result = summarise({"ifu_xacts": 0}, {"ifu_xacts": 200}, 100000)
        self.assertAlmostEqual(2.0, result["transfers_per_kilocycle"]["ifu_xacts"])


if __name__ == "__main__":
    unittest.main()
