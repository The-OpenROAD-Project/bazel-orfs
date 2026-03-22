"""Unit tests for the mock openroad binary."""

import os
import tempfile
import unittest

from mock_helpers import load_mock

mock_openroad = load_mock("openroad")


class TestExtractOutputFiles(unittest.TestCase):
    def test_write_db(self):
        tcl = "write_db $::env(RESULTS_DIR)/2_floorplan.odb"
        self.assertEqual(
            mock_openroad.extract_output_files(tcl),
            ["2_floorplan.odb"],
        )

    def test_orfs_write_db(self):
        tcl = "orfs_write_db $::env(RESULTS_DIR)/3_place.odb"
        self.assertEqual(
            mock_openroad.extract_output_files(tcl),
            ["3_place.odb"],
        )

    def test_write_sdc(self):
        tcl = "write_sdc -no_timestamp " "$::env(RESULTS_DIR)/2_floorplan.sdc"
        self.assertEqual(
            mock_openroad.extract_output_files(tcl),
            ["2_floorplan.sdc"],
        )

    def test_write_verilog(self):
        tcl = "write_verilog $::env(RESULTS_DIR)/6_final.v"
        self.assertEqual(
            mock_openroad.extract_output_files(tcl),
            ["6_final.v"],
        )

    def test_write_verilog_with_flags(self):
        tcl = (
            "write_verilog -remove_cells "
            "$::env(ASAP7_REMOVE_CELLS) "
            "$::env(RESULTS_DIR)/6_final.v"
        )
        self.assertEqual(
            mock_openroad.extract_output_files(tcl),
            ["6_final.v"],
        )

    def test_write_spef(self):
        tcl = "write_spef $::env(RESULTS_DIR)/6_final.spef"
        self.assertEqual(
            mock_openroad.extract_output_files(tcl),
            ["6_final.spef"],
        )

    def test_multiple_writes(self):
        tcl = (
            "write_db $::env(RESULTS_DIR)/4_cts.odb\n"
            "write_sdc -no_timestamp "
            "$::env(RESULTS_DIR)/4_cts.sdc\n"
        )
        result = mock_openroad.extract_output_files(tcl)
        self.assertEqual(result, ["4_cts.odb", "4_cts.sdc"])

    def test_no_writes(self):
        tcl = 'puts "hello world"'
        self.assertEqual(mock_openroad.extract_output_files(tcl), [])

    def test_empty(self):
        self.assertEqual(mock_openroad.extract_output_files(""), [])


class TestNeedsAbstract(unittest.TestCase):
    def test_abstract_lef(self):
        tcl = "write_abstract_lef -bloat_occupied_layers $p"
        self.assertTrue(mock_openroad.needs_abstract(tcl))

    def test_timing_model(self):
        tcl = "write_timing_model $lib_path"
        self.assertTrue(mock_openroad.needs_abstract(tcl))

    def test_both(self):
        tcl = (
            "write_abstract_lef -bloat_occupied_layers $l\n" "write_timing_model $lib\n"
        )
        self.assertTrue(mock_openroad.needs_abstract(tcl))

    def test_no_abstract(self):
        tcl = "write_db foo.odb"
        self.assertFalse(mock_openroad.needs_abstract(tcl))


class TestCreateOutputs(unittest.TestCase):
    def test_creates_odb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write("write_db " "$::env(RESULTS_DIR)/2_floorplan.odb\n")
            created = mock_openroad.create_outputs(tcl_path, results_dir)
            self.assertEqual(len(created), 1)
            self.assertTrue(
                os.path.exists(os.path.join(results_dir, "2_floorplan.odb"))
            )

    def test_creates_abstract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write("write_abstract_lef $lef\n" "write_timing_model $lib\n")
            mock_openroad.create_outputs(tcl_path, results_dir, "mydesign")
            self.assertTrue(os.path.exists(os.path.join(results_dir, "mydesign.lef")))
            self.assertTrue(
                os.path.exists(os.path.join(results_dir, "mydesign_typ.lib"))
            )

    def test_no_abstract_without_design_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write("write_abstract_lef $lef\n")
            created = mock_openroad.create_outputs(tcl_path, results_dir, "")
            self.assertEqual(len(created), 0)

    def test_no_results_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            with open(tcl_path, "w") as f:
                f.write("write_db " "$::env(RESULTS_DIR)/2_floorplan.odb\n")
            created = mock_openroad.create_outputs(tcl_path, "", "")
            self.assertEqual(created, [])

    def test_nonexistent_tcl(self):
        created = mock_openroad.create_outputs("/nonexistent.tcl", "/tmp/results")
        self.assertEqual(created, [])


class TestMain(unittest.TestCase):
    def test_version(self):
        self.assertEqual(mock_openroad.main(["-version"]), 0)

    def test_help(self):
        self.assertEqual(mock_openroad.main(["-help"]), 0)

    def test_no_args(self):
        self.assertEqual(mock_openroad.main([]), 0)

    def test_tcl_processing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tcl_path = os.path.join(tmpdir, "test.tcl")
            results_dir = os.path.join(tmpdir, "results")
            with open(tcl_path, "w") as f:
                f.write("write_db " "$::env(RESULTS_DIR)/2_floorplan.odb\n")
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


if __name__ == "__main__":
    unittest.main()
