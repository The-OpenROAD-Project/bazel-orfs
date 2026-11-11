#!/usr/bin/env python3
"""Unit tests for slice_memories.py"""

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import slice_memories

SLICE = """\
// verilog_slice: Outer Outer$Top.outer
// verilog_slice: Inner Inner$Top.outer.inner
module Leaf(
  input a
);
endmodule
module ram_8x4(
  input clk
);
endmodule
module Inner(
  input a
);
endmodule
module Outer(
  input a
);
endmodule
"""

LIB = 'library (ram_8x4) {\n    date : "2026-01-01 00:00:00Z";\n}\n'


def inventory(*records):
    return json.dumps({"version": 1, "platform": "asap7", "memories": list(records)})


class HelpersTest(unittest.TestCase):
    def test_slice_modules_leave_out_stubs(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.v"
            path.write_text(SLICE)
            self.assertEqual(
                slice_memories.slice_modules(path), ["Leaf", "ram_8x4", "Outer"]
            )

    def test_undated(self):
        self.assertEqual(
            slice_memories.undated(LIB), 'library (ram_8x4) {\n    date : "";\n}\n'
        )


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.design = root / "design"
        self.design.mkdir()
        self.slice_dir = root / "slice"
        self.slice_dir.mkdir()
        self.slice_v = root / "partition_Outer_slice.v"
        self.slice_v.write_text(SLICE)
        record = {"name": "ram_8x4", "rows": 8, "bits": 4}
        self.design_json = root / "memories.json"
        self.design_json.write_text(inventory(record))
        (self.design / "blackboxes.txt").write_text("ram_8x4 1.5\n")
        (self.design / "ram_8x4.lib").write_text(LIB)
        (self.slice_dir / "memories.json").write_text(inventory(record))
        (self.slice_dir / "blackboxes.txt").write_text("ram_8x4 1.5\n")
        (self.slice_dir / "ram_8x4.lib").write_text(slice_memories.undated(LIB))
        self.stamp = root / "ok"

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self):
        return slice_memories.main(
            [
                "check",
                "--global-dir",
                str(self.design),
                "--global-json",
                str(self.design_json),
                "--stamp",
                str(self.stamp),
                "--slice-dir",
                str(self.slice_dir),
                "--slice",
                str(self.slice_v),
            ]
        )

    def assert_fails(self, message):
        with mock.patch("sys.stderr") as err:
            self.assertEqual(self.run_check(), 1)
        self.assertFalse(self.stamp.exists())
        self.assertIn(message, "".join(c.args[0] for c in err.write.call_args_list))

    def test_agreeing_slice_passes(self):
        self.assertEqual(self.run_check(), 0)
        self.assertTrue(self.stamp.exists())

    def test_shape_from_outside_the_slice_fails(self):
        (self.slice_dir / "memories.json").write_text(
            inventory({"name": "ram_8x4", "rows": 16, "bits": 4})
        )
        self.assert_fails("depends on context outside the slice")

    def test_memory_the_slice_missed_fails(self):
        (self.slice_dir / "blackboxes.txt").write_text("")
        self.assert_fails("spans slices")

    def test_black_box_only_in_slice_fails(self):
        (self.slice_dir / "blackboxes.txt").write_text("ram_8x4 1.5\nghost 2\n")
        self.assert_fails("ghost is a black box here and not in the whole design")

    def test_view_that_differs_fails(self):
        (self.slice_dir / "ram_8x4.lib").write_text(LIB.replace("ram_8x4", "ram_9x4"))
        self.assert_fails("ram_8x4.lib differs")


class SliceTest(unittest.TestCase):
    """slice: ORFS's detection over the slice's netlist, scoped to it."""

    def test_overrides_and_regfiles_scoped_to_the_slice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            regfiles = root / "regfiles"
            regfiles.mkdir()
            (regfiles / "blackboxes.txt").write_text("rf_core 3.0\n")
            (regfiles / "inline.txt").write_text("rf\n")
            (regfiles / "rf.v").write_text("module rf(); endmodule\n")
            (regfiles / slice_memories.REGFILE_RECORDS).write_text("")
            slice_v = root / "s.v"
            slice_v.write_text(SLICE)
            overrides = root / "o.memories"
            overrides.write_text("")
            out = root / "out"

            mem = lambda name: types.SimpleNamespace(name=name, idiomatic=True)
            schema = mock.Mock()
            schema.load.side_effect = lambda p: (
                []
                if p.name == slice_memories.REGFILE_RECORDS
                else [mem("ram_8x4"), mem("elsewhere")]
            )
            schema.merge.side_effect = lambda found, over: list(found) + list(over)
            detect = mock.Mock()
            detect.scan_yosys_json.return_value = []
            detect.initialized_modules.return_value = set()
            gen = types.SimpleNamespace(FAKERAM_RUN_PY="run.py")

            def fakeram(argv):
                (out / "blackboxes.txt").write_text("ram_8x4 1.5\n")
                (out / "ram_8x4.lib").write_text(LIB)

            with mock.patch.object(
                slice_memories,
                "orfs_memories",
                return_value=(detect, gen, mock.Mock(), schema),
            ), mock.patch("subprocess.check_call", side_effect=fakeram) as call:
                rc = slice_memories.main(
                    [
                        "slice",
                        "--scripts-dir",
                        "scripts",
                        "--yosys-json",
                        "j.json",
                        "--top",
                        "Outer",
                        "--slice",
                        str(slice_v),
                        "--regfiles-dir",
                        str(regfiles),
                        "--out-dir",
                        str(out),
                        "--memories",
                        str(overrides),
                        "--platform",
                        "asap7",
                    ]
                )
            self.assertEqual(rc, 0)
            detect.scan_yosys_json.assert_called_once_with(Path("j.json"), "Outer")
            merged_overrides = schema.merge.call_args[0][1]
            self.assertEqual([m.name for m in merged_overrides], ["ram_8x4"])
            call.assert_called_once()
            self.assertEqual(
                (out / "blackboxes.txt").read_text(), "ram_8x4 1.5\nrf_core 3.0\n"
            )
            self.assertEqual((out / "rf.v").read_text(), "module rf(); endmodule\n")
            self.assertIn('date : "";', (out / "ram_8x4.lib").read_text())

    def test_initialized_register_file_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            regfiles = root / "regfiles"
            regfiles.mkdir()
            (regfiles / slice_memories.REGFILE_RECORDS).write_text("")
            schema = mock.Mock()
            schema.load.return_value = [types.SimpleNamespace(name="rf")]
            detect = mock.Mock()
            detect.scan_yosys_json.return_value = []
            detect.initialized_modules.return_value = {"rf"}
            with mock.patch.object(
                slice_memories,
                "orfs_memories",
                return_value=(detect, mock.Mock(), mock.Mock(), schema),
            ), mock.patch("sys.stderr") as err:
                rc = slice_memories.main(
                    [
                        "slice",
                        "--scripts-dir",
                        "scripts",
                        "--yosys-json",
                        "j.json",
                        "--top",
                        "Outer",
                        "--slice",
                        "s.v",
                        "--regfiles-dir",
                        str(regfiles),
                        "--out-dir",
                        str(root / "out"),
                        "--platform",
                        "asap7",
                    ]
                )
            self.assertEqual(rc, 1)
            self.assertIn(
                "initial value", "".join(c.args[0] for c in err.write.call_args_list)
            )


if __name__ == "__main__":
    unittest.main()
