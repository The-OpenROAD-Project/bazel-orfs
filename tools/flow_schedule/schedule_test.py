"""Unit tests for the at-home scheduler (schedule.py)."""

import os
import tempfile
import unittest

import schedule

LOG_TAIL = (
    "write_db ./results/asap7/Frontend/base/5_1_grt.odb\n"
    "Elapsed time: 1:02:03.60[h:]min:sec. CPU time: user 1.0 sys 1.0 (100%)."
    " Peak memory: 20971520KB.\n"
)


class Pack(unittest.TestCase):
    def test_fits_in_one_wave(self):
        self.assertEqual(schedule.pack({"a": 10, "b": 20}, 40), [["b", "a"]])

    def test_splits_by_budget_largest_first(self):
        waves = schedule.pack({"a": 30, "b": 30, "c": 10}, 45)
        self.assertEqual(waves, [["a", "c"], ["b"]])

    def test_over_budget_unit_alone(self):
        self.assertEqual(schedule.pack({"big": 100, "s": 5}, 50), [["big"], ["s"]])


class Peaks(unittest.TestCase):
    def test_estimate_is_padded(self):
        e = {"source": "estimated", "stages": {"grt": {"peak_gb": 10}}}
        self.assertAlmostEqual(schedule.unit_peak(e), 12.0)

    def test_measured_is_not(self):
        e = {
            "source": "measured",
            "stages": {"cts": {"peak_gb": 8}, "grt": {"peak_gb": 10}},
        }
        self.assertEqual(schedule.unit_peak(e), 10)


class Logs(unittest.TestCase):
    def test_parse_hours(self):
        peak, minutes = schedule.parse_log(LOG_TAIL)
        self.assertAlmostEqual(peak, 20.0)
        self.assertAlmostEqual(minutes, 62.06, places=2)

    def test_parse_minutes_only(self):
        got = schedule.parse_log(
            "Elapsed time: 0:29.88[h:]min:sec. CPU time: x. Peak memory: 1048576KB.\n"
        )
        self.assertAlmostEqual(got[0], 1.0)
        self.assertAlmostEqual(got[1], 0.498, places=3)

    def test_no_elapsed(self):
        self.assertIsNone(schedule.parse_log("nothing here\n"))

    def test_measure_stage_dir(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in [
                ("4_1_cts.log", LOG_TAIL.replace("20971520", "10485760")),
                ("5_1_grt.log", LOG_TAIL),
                ("5_2_route.log", LOG_TAIL.replace("20971520", "31457280")),
                ("notes.txt", LOG_TAIL),
            ]:
                with open(os.path.join(d, name), "w") as f:
                    f.write(text)
            got = schedule.measure(d)
        self.assertEqual(set(got), {"cts", "grt"})
        self.assertEqual(got["cts"]["peak_gb"], 10.0)
        # two grt steps: the larger peak, the summed time
        self.assertEqual(got["grt"]["peak_gb"], 30.0)
        self.assertAlmostEqual(got["grt"]["minutes"], 124.1, delta=0.2)


class Refresh(unittest.TestCase):
    MEASURED = {"grt": {"peak_gb": 20.0, "minutes": 60.0}}

    def test_estimate_becomes_measured(self):
        old = {"source": "estimated", "stages": {"grt": {"peak_gb": 30, "minutes": 90}}}
        new, changed = schedule.refresh(old, self.MEASURED)
        self.assertTrue(changed)
        self.assertEqual(new["source"], "measured")

    def test_close_measurement_kept(self):
        old = {
            "source": "measured",
            "stages": {"grt": {"peak_gb": 19.0, "minutes": 58.0}},
        }
        new, changed = schedule.refresh(old, self.MEASURED)
        self.assertFalse(changed)
        self.assertIs(new, old)

    def test_far_measurement_rewritten(self):
        old = {
            "source": "measured",
            "stages": {"grt": {"peak_gb": 12.0, "minutes": 60.0}},
        }
        _, changed = schedule.refresh(old, self.MEASURED)
        self.assertTrue(changed)

    def test_partial_run_keeps_estimates(self):
        old = {
            "source": "estimated",
            "basis": "x",
            "stages": {
                "cts": {"peak_gb": 25, "minutes": 160},
                "grt": {"peak_gb": 35, "minutes": 60},
            },
        }
        new, changed = schedule.refresh(
            old, {"floorplan": {"peak_gb": 10.1, "minutes": 36.4}}, complete=False
        )
        self.assertTrue(changed)
        self.assertEqual(new["source"], "estimated")
        self.assertEqual(schedule.unit_peak(new), 35 * schedule.ESTIMATE_PAD)
        self.assertIn("floorplan", new["stages"])

    def test_nothing_measured(self):
        old = {"source": "estimated", "stages": {"grt": {"peak_gb": 30}}}
        self.assertEqual(schedule.refresh(old, {}), (old, False))


class Units(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(
            schedule.parse_units(["A=//p:a,//p:b", "B=//p:c"]),
            {"A": ["//p:a", "//p:b"], "B": ["//p:c"]},
        )

    def test_bad(self):
        with self.assertRaises(SystemExit):
            schedule.parse_units(["nope"])


if __name__ == "__main__":
    unittest.main()
