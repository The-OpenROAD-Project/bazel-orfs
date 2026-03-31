"""Unit tests for the mock openroad binary."""

import os
import tempfile
import unittest

from mock_helpers import load_mock

mock_openroad = load_mock("openroad")


class TestMain(unittest.TestCase):
    def test_version(self):
        self.assertEqual(mock_openroad.main(["-version"]), 0)

    def test_help(self):
        self.assertEqual(mock_openroad.main(["-help"]), 0)

    def test_no_args(self):
        self.assertEqual(mock_openroad.main([]), 0)

    def test_tcl_creates_odb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write("write_db $::env(RESULTS_DIR)/2_floorplan.odb\n")
            old_env = os.environ.copy()
            os.environ["RESULTS_DIR"] = results_dir
            os.environ["DESIGN_NAME"] = "test"
            try:
                rc = mock_openroad.main([tcl_path])
                self.assertEqual(rc, 0)
                self.assertTrue(
                    os.path.exists(os.path.join(results_dir, "2_floorplan.odb"))
                )
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_tcl_creates_sdc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write(
                    "write_sdc -no_timestamp " "$::env(RESULTS_DIR)/2_floorplan.sdc\n"
                )
            old_env = os.environ.copy()
            os.environ["RESULTS_DIR"] = results_dir
            os.environ["DESIGN_NAME"] = "test"
            try:
                rc = mock_openroad.main([tcl_path])
                self.assertEqual(rc, 0)
                self.assertTrue(
                    os.path.exists(os.path.join(results_dir, "2_floorplan.sdc"))
                )
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_tcl_creates_multiple_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write(
                    "write_db $::env(RESULTS_DIR)/4_cts.odb\n"
                    "write_sdc -no_timestamp "
                    "$::env(RESULTS_DIR)/4_cts.sdc\n"
                )
            old_env = os.environ.copy()
            os.environ["RESULTS_DIR"] = results_dir
            os.environ["DESIGN_NAME"] = "test"
            try:
                rc = mock_openroad.main([tcl_path])
                self.assertEqual(rc, 0)
                self.assertTrue(os.path.exists(os.path.join(results_dir, "4_cts.odb")))
                self.assertTrue(os.path.exists(os.path.join(results_dir, "4_cts.sdc")))
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_tcl_creates_verilog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write("write_verilog $::env(RESULTS_DIR)/6_final.v\n")
            old_env = os.environ.copy()
            os.environ["RESULTS_DIR"] = results_dir
            os.environ["DESIGN_NAME"] = "test"
            try:
                rc = mock_openroad.main([tcl_path])
                self.assertEqual(rc, 0)
                self.assertTrue(os.path.exists(os.path.join(results_dir, "6_final.v")))
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_tcl_creates_spef(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write("write_spef $::env(RESULTS_DIR)/6_final.spef\n")
            old_env = os.environ.copy()
            os.environ["RESULTS_DIR"] = results_dir
            os.environ["DESIGN_NAME"] = "test"
            try:
                rc = mock_openroad.main([tcl_path])
                self.assertEqual(rc, 0)
                self.assertTrue(
                    os.path.exists(os.path.join(results_dir, "6_final.spef"))
                )
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_nonexistent_tcl(self):
        rc = mock_openroad.main(["/nonexistent.tcl"])
        self.assertEqual(rc, 0)

    def test_flags_ignored(self):
        rc = mock_openroad.main(["-exit", "-threads", "4", "-no_init"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
