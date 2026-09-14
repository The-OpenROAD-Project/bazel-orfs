"""Unit tests for the initial-place log parser, against real ORFS logs."""

import os
import unittest

import initial_place

HERE = os.path.dirname(os.path.abspath(__file__))


def fixture(name):
    with open(os.path.join(HERE, "testdata", name), errors="replace") as handle:
        return handle.read()


class TrajectoryTest(unittest.TestCase):
    def test_reads_every_outer_iteration(self):
        rows = initial_place.trajectory(fixture("place_gp_shipped.log"))
        self.assertEqual([row["iteration"] for row in rows], [1, 2, 3, 4, 5])
        self.assertEqual(rows[0]["hpwl"], 721133)
        self.assertEqual(rows[-1]["hpwl"], 637513)

    def test_residuals_are_parsed_as_floats(self):
        rows = initial_place.trajectory(fixture("place_gp_shipped.log"))
        self.assertAlmostEqual(rows[0]["residual"], 1.1e-7, delta=1e-8)

    def test_a_log_without_initial_place_yields_nothing(self):
        self.assertEqual(initial_place.trajectory("no placement here"), [])


class ConvergenceTest(unittest.TestCase):
    def test_gcd_meets_the_residual_immediately_and_stops_at_the_floor(self):
        # The break is `residual <= 1e-5 && iter >= 5`. On this design the
        # linear solve is already at 1e-7 on iteration 1, so the loop runs
        # only because of the iteration floor and never approaches the
        # -initial_place_max_iter cap of 20.
        out = initial_place.convergence(fixture("place_gp_shipped.log"))
        self.assertTrue(out["converged"])
        self.assertFalse(out["hit_cap"])
        self.assertEqual(out["iterations"], 5)
        self.assertEqual(out["last_iteration"], 5)
        self.assertLess(out["final_residual"], initial_place.CONVERGENCE_RESIDUAL)

    def test_hpwl_endpoints_are_carried(self):
        out = initial_place.convergence(fixture("place_gp_shipped.log"))
        self.assertEqual(out["hpwl_first"], 721133)
        self.assertEqual(out["hpwl_last"], 637513)

    def test_hitting_the_cap_is_distinguished_from_converging(self):
        text = "\n".join(
            "[InitialPlace]  Iter: %d conjugate gradient residual: 0.50000000 "
            "HPWL: %d" % (i, 1000 + i)
            for i in range(1, 21)
        )
        out = initial_place.convergence(text, max_iter=20)
        self.assertFalse(out["converged"])
        self.assertTrue(out["hit_cap"])

    def test_a_nan_residual_is_not_read_as_unconverged(self):
        # NaN compares false against every threshold, so a caller that
        # skipped this check would silently report "did not converge"
        # when the truth is that the solve failed.
        text = (
            "[InitialPlace]  Iter: 1 conjugate gradient residual: nan HPWL: 10\n"
            "[WARNING GPL-0325] Conjugate gradient initial placement solver "
            "failed at iteration 1."
        )
        out = initial_place.convergence(text)
        self.assertIsNone(out["final_residual"])
        self.assertTrue(out["nan"])
        self.assertFalse(out["converged"])

    def test_no_initial_place_returns_none(self):
        self.assertIsNone(initial_place.convergence("nothing"))


class PositionSourceTest(unittest.TestCase):
    def test_reads_the_gpl_51_counters(self):
        out = initial_place.position_sources(fixture("place_gp_shipped.log"))
        self.assertEqual(out, {"odb": 0, "core_center": 314, "region_center": 0})

    def test_orfs_forces_every_cell_to_the_core_center_at_3_3(self):
        # The flow-wide -force_center_initial_place ORFS appends means
        # 3_1's converged placement reaches 3_3 and is then discarded.
        # If this ever stops being true the study's premise changes, so
        # it is asserted rather than assumed.
        out = initial_place.position_sources(fixture("place_gp_shipped.log"))
        self.assertEqual(out["odb"], 0)

    def test_a_mode_arm_has_no_gpl_51_line(self):
        self.assertIsNone(
            initial_place.position_sources(fixture("place_gp_anchored.log"))
        )


class ModeWitnessTest(unittest.TestCase):
    def test_reads_the_study_patch_witness(self):
        out = initial_place.mode_witness(fixture("place_gp_anchored.log"))
        self.assertEqual(out["mode"], "anchored")
        self.assertEqual(out["placed"], 314)
        self.assertEqual(out["anchored"], 87)
        self.assertEqual(out["seed"], 1)

    def test_shipped_path_has_no_witness(self):
        self.assertIsNone(initial_place.mode_witness(fixture("place_gp_shipped.log")))


class WitnessedArmTest(unittest.TestCase):
    def test_mode_arm_names_itself(self):
        self.assertEqual(
            initial_place.witnessed_arm(fixture("place_gp_anchored.log")), "anchored"
        )

    def test_shipped_path_is_named_shipped(self):
        self.assertEqual(
            initial_place.witnessed_arm(fixture("place_gp_shipped.log")), "shipped"
        )

    def test_a_log_with_neither_witness_is_unattributable(self):
        # This is the case that must not be silently credited to an arm:
        # a flag that never reached the command line produces a perfectly
        # normal run that looks exactly like the default.
        self.assertIsNone(initial_place.witnessed_arm("some other tool's log"))


if __name__ == "__main__":
    unittest.main()
