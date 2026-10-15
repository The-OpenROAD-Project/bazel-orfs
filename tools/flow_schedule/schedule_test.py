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


class OomdKiller(unittest.TestCase):
    """oomd_killer reads files only; a fake socket, cgroup and unit tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.socket = os.path.join(d, "io.systemd.ManagedOOM")
        open(self.socket, "w").close()
        self.cgroup = os.path.join(d, "cgroup")
        with open(self.cgroup, "w") as f:
            f.write(
                "0::/user.slice/user-1000.slice/user@1000.service/app.slice/x.scope\n"
            )
        self.units = os.path.join(d, "system")
        dropins = os.path.join(self.units, "user@.service.d")
        os.makedirs(dropins)
        with open(
            os.path.join(dropins, "10-oomd-user-service-defaults.conf"), "w"
        ) as f:
            f.write("[Service]\nManagedOOMMemoryPressure=kill\n")

    def tearDown(self):
        self.tmp.cleanup()

    def killer(self, socket=None):
        return schedule.oomd_killer(self.cgroup, socket or self.socket, (self.units,))

    def test_ubuntu_user_service_template(self):
        got = self.killer()
        self.assertIn("ManagedOOMMemoryPressure=kill on user@1000.service", got)

    def test_none_when_oomd_stopped(self):
        self.assertIsNone(self.killer(socket=os.path.join(self.tmp.name, "gone")))

    def test_none_outside_a_killing_unit(self):
        with open(self.cgroup, "w") as f:
            f.write("0::/system.slice/build.service\n")
        self.assertIsNone(self.killer())


class Preflight(unittest.TestCase):
    KILLER = "systemd-oomd: ManagedOOMMemoryPressure=kill on user@1000.service"

    def test_fits_in_ram(self):
        waves = [("macros", ["a"]), ("parent", ["p"])]
        got = schedule.preflight(waves, {"a": 30, "p": 50}, 60, 250, 5, self.KILLER)
        self.assertEqual(got, [])

    def test_pages_without_a_killer(self):
        got = schedule.preflight([("parent", ["p"])], {"p": 120}, 60, 250, 5, None)
        self.assertEqual(got, [])

    def test_pages_under_oomd(self):
        got = schedule.preflight(
            [("parent", ["p"])], {"p": 120}, 60, 250, 5, self.KILLER
        )
        self.assertEqual(len(got), 1)
        self.assertIn("pages", got[0])
        self.assertIn("systemctl stop systemd-oomd.socket", got[0])

    def test_beyond_ram_and_swap(self):
        got = schedule.preflight([("parent", ["p"])], {"p": 400}, 60, 250, 5, None)
        self.assertEqual(len(got), 1)
        self.assertIn("more than free RAM and swap", got[0])


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


class Run(unittest.TestCase):
    WAVES = [("macros", ["A"]), ("macros", ["B"]), ("parent", ["P"])]
    MACROS = {"A": ["//p:a"], "B": ["//p:b"]}
    PARENTS = {"P": ["//p:p"]}

    def run_with(self, failing):
        built = []

        def build(i, wave, targets):
            built.append(targets)
            return 1 if wave[0] in failing else 0

        results = schedule.run(self.WAVES, self.MACROS, self.PARENTS, build)
        return results, built

    def test_all_waves(self):
        results, built = self.run_with(set())
        self.assertEqual(results, {1: 0, 2: 0, 3: 0})
        self.assertEqual(built, [["//p:a"], ["//p:b"], ["//p:p"]])

    def test_failed_macro_wave_skips_only_the_parent(self):
        results, built = self.run_with({"A"})
        self.assertEqual(results, {1: 1, 2: 0})
        self.assertEqual(built, [["//p:a"], ["//p:b"]])


if __name__ == "__main__":
    unittest.main()
