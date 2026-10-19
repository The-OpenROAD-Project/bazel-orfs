"""export_design's merge and rewrite rules, on a synthetic execroot."""

import os
import tempfile
import unittest

import export_design
from export_design import Inputs, Refused, merge


class MergeTest(unittest.TestCase):
    def test_union_of_the_stages(self):
        merged = merge(
            [
                ("synth", {"DESIGN_NAME": "gcd", "SYNTH_USE_SYN": "1"}),
                ("floorplan", {"DESIGN_NAME": "gcd", "CORE_UTILIZATION": "65"}),
            ]
        )
        self.assertEqual(
            merged,
            {"DESIGN_NAME": "gcd", "SYNTH_USE_SYN": "1", "CORE_UTILIZATION": "65"},
        )

    def test_drops_what_the_orfs_install_supplies(self):
        merged = merge(
            [
                ("synth", {"PLATFORM_DIR": "external/orfs/flow/platforms/asap7"}),
                ("floorplan", {"PLATFORM_DIR": "external/orfs/flow/x/platforms/asap7"}),
                ("place", {"WORK_HOME": "./pkg", "FLOW_VARIANT": "base"}),
            ]
        )
        self.assertEqual(merged, {})

    def test_refuses_two_values(self):
        with self.assertRaises(Refused) as e:
            merge([("floorplan", {"X": "1"}), ("place", {"X": "2"})])
        self.assertIn("X is '1' in floorplan but '2' in place", str(e.exception))
        self.assertIn("export_design.py is the file to patch", str(e.exception))


class InputsTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        self.execroot = os.path.join(self.root, "execroot")
        self.dest = os.path.join(self.root, "dest")
        for p in ["pkg/rtl/top.v", "bazel-out/bin/pkg/gen.v", "other/c.sdc"]:
            os.makedirs(os.path.dirname(os.path.join(self.execroot, p)), exist_ok=True)
            with open(os.path.join(self.execroot, p), "w") as f:
                f.write(p)
        manifest = {
            "_main/pkg/rtl/top.v": ("pkg/rtl/top.v", "input"),
            "_main/pkg/gen.v": ("bazel-out/bin/pkg/gen.v", "input"),
            "_main/other/c.sdc": ("other/c.sdc", "input"),
            "_main/external/orfs/flow/platforms/asap7/lef/m.lef": (
                "external/orfs/flow/platforms/asap7/lef/m.lef",
                "input",
            ),
            "_main/pkg/results/asap7/top/base/1_synth.odb": (
                "bazel-out/bin/pkg/results/asap7/top/base/1_synth.odb",
                "result",
            ),
        }
        self.inputs = Inputs(self.execroot, self.dest, manifest, "asap7", "pkg")

    def test_copies_inputs_under_their_package_path(self):
        value = self.inputs.rewrite("VERILOG_FILES", "pkg/rtl/top.v pkg/gen.v")
        self.assertEqual(
            value,
            "$(EXPORT_DIR)/inputs/rtl/top.v $(EXPORT_DIR)/inputs/gen.v",
        )
        with open(os.path.join(self.dest, "inputs", "gen.v")) as f:
            self.assertEqual(f.read(), "bazel-out/bin/pkg/gen.v")

    def test_another_package_keeps_its_path(self):
        self.assertEqual(
            self.inputs.rewrite("SDC_FILE", "other/c.sdc"),
            "$(EXPORT_DIR)/inputs/other/c.sdc",
        )

    def test_platform_files_stay_the_platforms(self):
        self.assertEqual(
            self.inputs.rewrite(
                "ADDITIONAL_LEFS", "external/orfs/flow/platforms/asap7/lef/m.lef"
            ),
            "$(PLATFORM_DIR)/lef/m.lef",
        )

    def test_literals_pass(self):
        self.assertEqual(self.inputs.rewrite("CORE_AREA", "2 2 23 23"), "2 2 23 23")

    def test_refuses_an_earlier_stages_result(self):
        with self.assertRaises(Refused) as e:
            self.inputs.rewrite("ODB", "pkg/results/asap7/top/base/1_synth.odb")
        self.assertIn("an earlier stage's result", str(e.exception))


class ConfigTest(unittest.TestCase):
    def test_refuses_a_line_it_does_not_read(self):
        path = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")), "c.mk")
        with open(path, "w") as f:
            f.write("export A?=1\nifeq ($(A),1)\n")
        with self.assertRaises(Refused):
            export_design.read_config(path)

    def test_reads_exports_and_includes(self):
        path = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")), "c.mk")
        with open(path, "w") as f:
            f.write("export A?=1 2\ninclude pkg/extra.mk\n")
        self.assertEqual(
            export_design.read_config(path), ({"A": "1 2"}, ["pkg/extra.mk"])
        )


if __name__ == "__main__":
    unittest.main()
