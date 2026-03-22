"""Unit tests for the mock klayout binary."""

import os
import tempfile
import unittest

from mock_helpers import load_mock

mock_klayout = load_mock("klayout")


class TestParseRdArgs(unittest.TestCase):
    def test_single_rd(self):
        args = ["-rd", "out=/tmp/test.gds"]
        self.assertEqual(
            mock_klayout.parse_rd_args(args),
            {"out": "/tmp/test.gds"},
        )

    def test_multiple_rd(self):
        args = ["-rd", "design_name=foo", "-rd", "out_file=/t.gds"]
        result = mock_klayout.parse_rd_args(args)
        self.assertEqual(
            result,
            {"design_name": "foo", "out_file": "/t.gds"},
        )

    def test_no_rd(self):
        args = ["-b", "-r", "script.py"]
        self.assertEqual(mock_klayout.parse_rd_args(args), {})

    def test_rd_at_end_without_value(self):
        args = ["-b", "-rd"]
        self.assertEqual(mock_klayout.parse_rd_args(args), {})

    def test_mixed_args(self):
        args = [
            "-zz",
            "-rd",
            "in_gds=input.gds",
            "-r",
            "drc.py",
            "-rd",
            "out=out.gds",
        ]
        result = mock_klayout.parse_rd_args(args)
        self.assertEqual(
            result,
            {"in_gds": "input.gds", "out": "out.gds"},
        )

    def test_value_with_equals(self):
        args = ["-rd", "out=/path/with=equals.gds"]
        result = mock_klayout.parse_rd_args(args)
        self.assertEqual(result, {"out": "/path/with=equals.gds"})


class TestCreateGds(unittest.TestCase):
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.gds")
            mock_klayout.create_gds(path)
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "test.gds")
            mock_klayout.create_gds(path)
            self.assertTrue(os.path.exists(path))

    def test_gds_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.gds")
            mock_klayout.create_gds(path)
            with open(path, "rb") as f:
                data = f.read()
            self.assertEqual(data, mock_klayout.GDS_HEADER)


class TestMain(unittest.TestCase):
    def test_version(self):
        self.assertEqual(mock_klayout.main(["-v"]), 0)

    def test_no_args(self):
        self.assertEqual(mock_klayout.main([]), 0)

    def test_creates_out_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "test.gds")
            result = mock_klayout.main(["-b", "-rd", f"out={outpath}", "-r", "s.py"])
            self.assertEqual(result, 0)
            self.assertTrue(os.path.exists(outpath))

    def test_creates_out_file_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = os.path.join(tmpdir, "test.gds")
            result = mock_klayout.main(["-zz", "-rd", f"out_file={outpath}"])
            self.assertEqual(result, 0)
            self.assertTrue(os.path.exists(outpath))

    def test_no_output_without_out_key(self):
        result = mock_klayout.main(["-rd", "in_gds=foo.gds"])
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
