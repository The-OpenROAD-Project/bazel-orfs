#!/usr/bin/env python3

"""Tests for schedule.py.

The scheduling model is the part of this study most likely to be quoted
out of context ("the gate takes 9 minutes"), so its arithmetic is pinned
here: the anchor must reproduce itself, more threads must help but
sub-linearly, and memory must be able to bind before cores do.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import schedule


class Runtime(unittest.TestCase):
    def setUp(self):
        self.m = schedule.Model()

    def test_anchor_reproduces_itself(self):
        # The one real measurement must come back out of the model.
        got = self.m.minutes(self.m.anchor_instances, self.m.anchor_threads)
        self.assertAlmostEqual(got, self.m.anchor_minutes, places=6)

    def test_more_threads_is_faster_but_sublinear(self):
        one = self.m.minutes(100000, 1)
        eight = self.m.minutes(100000, 8)
        self.assertLess(eight, one)
        self.assertGreater(eight, one / 8, "speedup cannot beat Amdahl")

    def test_serial_fraction_caps_the_speedup(self):
        m = schedule.Model(serial_fraction=0.5)
        self.assertLess(m.speedup(10**6), 2.0 + 1e-6)

    def test_bigger_designs_take_superlinearly_longer(self):
        ten_x = self.m.minutes(180000, 10) / self.m.minutes(18000, 10)
        self.assertGreater(ten_x, 10.0)

    def test_tiny_designs_hit_the_floor(self):
        self.assertEqual(self.m.minutes(1, 8), self.m.floor_minutes)

    def test_memory_grows_with_size_from_a_base(self):
        self.assertGreater(self.m.memory_gb(10**6), self.m.memory_gb(10**3))
        self.assertAlmostEqual(self.m.memory_gb(0), self.m.base_gb)


class Makespan(unittest.TestCase):
    def test_wide_machine_is_just_the_longest_job(self):
        self.assertAlmostEqual(schedule.makespan([1, 5, 3], 10), 5)

    def test_one_slot_is_the_sum(self):
        self.assertAlmostEqual(schedule.makespan([1, 5, 3], 1), 9)

    def test_packing_beats_naive_chunking(self):
        # Two slots, jobs 4,3,3,2: optimal is 6, not 7.
        self.assertLessEqual(schedule.makespan([4, 3, 3, 2], 2), 6.0)

    def test_zero_slots_is_refused(self):
        with self.assertRaises(ValueError):
            schedule.makespan([1], 0)


class Scheduling(unittest.TestCase):
    SIZES = {"a/one": 500, "a/two": 500, "b/big": 200000}

    def test_memory_can_bind_before_cores(self):
        model = schedule.Model(base_gb=8.0, gb_per_instance=0.0)
        got = schedule.schedule(
            list(self.SIZES),
            self.SIZES,
            model,
            vcpus=128,
            memory_gb=16,
            threads_per_design=1,
        )
        self.assertEqual(got["limited_by"], "memory")
        self.assertEqual(got["slots"], 2)

    def test_cores_bind_when_memory_is_plentiful(self):
        got = schedule.schedule(
            list(self.SIZES),
            self.SIZES,
            schedule.Model(),
            vcpus=8,
            memory_gb=1024,
            threads_per_design=2,
        )
        self.assertEqual(got["limited_by"], "cores")

    def test_there_is_always_at_least_one_slot(self):
        got = schedule.schedule(
            list(self.SIZES),
            self.SIZES,
            schedule.Model(base_gb=99.0),
            vcpus=2,
            memory_gb=1,
            threads_per_design=1,
        )
        self.assertEqual(got["slots"], 1)

    def test_best_threading_never_exceeds_the_machine(self):
        got = schedule.best_threading(
            list(self.SIZES), self.SIZES, schedule.Model(), vcpus=8, memory_gb=512
        )
        self.assertLessEqual(got["threads_per_design"], 4)  # 8 vCPU / smt 2

    def test_best_threading_beats_the_worst_choice(self):
        designs, sizes = [], {}
        for i in range(16):
            designs.append(f"p/d{i}")
            sizes[f"p/d{i}"] = 20000
        best = schedule.best_threading(designs, sizes, schedule.Model(), 64, 512)
        worst = schedule.schedule(designs, sizes, schedule.Model(), 64, 512, 32)
        self.assertLess(best["wall_minutes"], worst["wall_minutes"])


if __name__ == "__main__":
    unittest.main()
