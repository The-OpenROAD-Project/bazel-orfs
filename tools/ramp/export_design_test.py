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


class StripBlocksTest(unittest.TestCase):
    PREFIXES = ["pkg/results/asap7/BlockA/"]

    def test_takes_out_the_blocks_abstracts(self):
        self.assertEqual(
            export_design.strip_blocks(
                {
                    "ADDITIONAL_LEFS": "pkg/results/asap7/BlockA/base/BlockA.lef m.lef",
                    "ADDITIONAL_LIBS": "pkg/results/asap7/BlockA/pre_layout/BlockA_typ.lib",
                    "CORE_UTILIZATION": "40",
                },
                self.PREFIXES,
            ),
            {"ADDITIONAL_LEFS": "m.lef", "CORE_UTILIZATION": "40"},
        )

    def test_pre_layout_and_abstract_libs_merge_once_taken_out(self):
        stages = [
            (
                "place",
                {
                    "ADDITIONAL_LIBS": "pkg/results/asap7/BlockA/pre_layout/BlockA_typ.lib"
                },
            ),
            (
                "cts",
                {"ADDITIONAL_LIBS": "pkg/results/asap7/BlockA/base/BlockA_typ.lib"},
            ),
        ]
        with self.assertRaises(Refused):
            merge(stages)
        self.assertEqual(
            merge(
                [(s, export_design.strip_blocks(e, self.PREFIXES)) for s, e in stages]
            ),
            {},
        )

    def test_refuses_a_block_file_elsewhere(self):
        with self.assertRaises(Refused) as e:
            export_design.strip_blocks(
                {"MACRO_PLACEMENT_TCL": "pkg/results/asap7/BlockA/base/x.tcl"},
                self.PREFIXES,
            )
        self.assertIn("MACRO_PLACEMENT_TCL names a block's result", str(e.exception))

    def test_another_flows_results_stay(self):
        exports = {"ADDITIONAL_LEFS": "pkg/results/asap7/BlockAB/base/BlockAB.lef"}
        self.assertEqual(export_design.strip_blocks(exports, self.PREFIXES), exports)


class StripPreLayoutTest(unittest.TestCase):
    PRE = "pkg/results/asap7/BlockA/unmocked_pre_layout/BlockA_typ.lib"
    OWN = "pkg/results/asap7/BlockA/unmocked/BlockA_typ.lib"

    def test_abstracts_keep_the_abstracts_own_lib(self):
        stages = export_design.strip_pre_layout(
            [
                ("place", {"ADDITIONAL_LIBS": self.PRE}),
                ("cts", {"ADDITIONAL_LIBS": self.OWN}),
            ]
        )
        self.assertEqual(merge(stages), {"ADDITIONAL_LIBS": self.OWN})

    def test_a_flow_that_ends_before_cts_keeps_its_only_lib(self):
        stages = [("floorplan", {"ADDITIONAL_LIBS": self.PRE})]
        self.assertEqual(export_design.strip_pre_layout(stages), stages)

    def test_an_empty_value_is_a_value(self):
        stages = [("floorplan", {"TAPCELL_TCL": "", "ADDITIONAL_LIBS": self.PRE})]
        self.assertEqual(export_design.strip_pre_layout(stages), stages)


class NetlistTest(unittest.TestCase):
    def test_a_yosys_flow_ships_its_netlist(self):
        self.assertTrue(export_design.wants_netlist({"DESIGN_NAME": "mac"}))

    def test_not_for_openroad_synthesis(self):
        self.assertFalse(export_design.wants_netlist({"SYNTH_USE_SYN": "1"}))

    def test_not_over_a_flows_own(self):
        self.assertFalse(
            export_design.wants_netlist({"SYNTH_NETLIST_FILES": "pkg/n.v"})
        )


class StartTest(unittest.TestCase):
    def test_earlier_results_land_in_orfs_work_tree(self):
        entries = {
            "_main/pkg/results/asap7/mac/base/3_place.odb": (
                "bazel-out/k8/bin/pkg/results/asap7/mac/base/3_place.odb",
                "result",
            ),
            "_main/pkg/objects/asap7/mac/base/lib/merged.lib": (
                "bazel-out/k8/bin/pkg/objects/asap7/mac/base/lib/merged.lib",
                "result",
            ),
            "_main/pkg/mac.v": ("bazel-out/k8/bin/pkg/mac.v", "input"),
        }
        self.assertEqual(
            export_design.start_files(entries, "asap7", "mac_nick"),
            [
                (
                    "bazel-out/k8/bin/pkg/objects/asap7/mac/base/lib/merged.lib",
                    "objects/asap7/mac_nick/base/lib/merged.lib",
                ),
                (
                    "bazel-out/k8/bin/pkg/results/asap7/mac/base/3_place.odb",
                    "results/asap7/mac_nick/base/3_place.odb",
                ),
            ],
        )

    def test_make_starts_where_asked(self):
        dest = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        lines = export_design.next_step(
            dest, {"PLATFORM": "asap7"}, "final", "cts", ["do-cts", "do-grt"]
        )
        self.assertEqual(
            lines[0], "next:   cp -rp {}/start/cts/. <ORFS>/flow/".format(dest)
        )
        self.assertTrue(lines[1].endswith("config.mk do-cts do-grt"))


class ExportMdTest(unittest.TestCase):
    SHOW_REPO = """## @orfs:
http_archive(
  name = "+orfs_repositories+orfs",
  patches = [Label("//patches:0039-orfs-a.patch"), Label("//patches:0068-orfs-b.patch")],
  urls = ["https://github.com/o/ORFS/archive/abc.tar.gz"],
)

## @yosys:
http_archive(
  urls = ["https://github.com/YosysHQ/yosys/releases/download/v0.68/yosys.tar.gz"],
  remote_patches = {"https://r/p1.patch": "sha256-x", "https://r/p2.patch": "sha256-y"},
  patches = [Label("//patches:yosys-0001.patch")],
)
"""

    def test_reads_sources_and_patches_in_order(self):
        repos = export_design.parse_show_repo(self.SHOW_REPO)
        self.assertEqual(
            repos["@orfs"],
            (
                "https://github.com/o/ORFS/archive/abc.tar.gz",
                ["//patches:0039-orfs-a.patch", "//patches:0068-orfs-b.patch"],
                0,
            ),
        )
        self.assertEqual(repos["@yosys"][1:], (["//patches:yosys-0001.patch"], 2))

    def test_says_what_made_it_without_a_local_path(self):
        dest = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        steps = export_design.next_step(
            "<this directory>", {"PLATFORM": "asap7"}, "final"
        )
        text = export_design.export_md(
            "//pkg:mac",
            "--snapshot-macro-placement <dest> //pkg:mac",
            "abc123",
            [("ORFS", "https://o/abc.tar.gz", ["patches/orfs/0001-a.patch"], 0)],
            steps,
        )
        self.assertIn("at abc123", text)
        self.assertIn("| ORFS | https://o/abc.tar.gz | 1 in `patches/orfs/` |", text)
        self.assertIn("DESIGN_CONFIG=<this directory>/config.mk", text)
        self.assertNotIn(dest, text)


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

    def test_a_file_bazel_built_is_generated(self):
        self.inputs.rewrite("VERILOG_FILES", "pkg/rtl/top.v pkg/gen.v")
        self.inputs.rewrite("SDC_FILE", "other/c.sdc")
        self.assertEqual(self.inputs.generated, {"VERILOG_FILES"})

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


class OrfsTest(unittest.TestCase):
    """Where an export lands in an ORFS checkout, and what it says to run."""

    def setUp(self):
        self.flow = os.path.join(
            tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")), "flow"
        )
        os.makedirs(os.path.join(self.flow, "scripts"))
        open(os.path.join(self.flow, "Makefile"), "w").close()
        open(os.path.join(self.flow, "scripts", "variables.mk"), "w").close()
        self.dest = os.path.join(self.flow, "designs", "asap7", "gcd-bazel")
        os.makedirs(self.dest)
        self.merged = {"PLATFORM": "asap7", "DESIGN_NAME": "gcd"}

    def test_make_as_usual_in_flow(self):
        self.assertEqual(
            export_design.next_step(self.dest, self.merged, "final"),
            [
                "next:   cd " + self.flow,
                "        make DESIGN_CONFIG=./designs/asap7/gcd-bazel/config.mk",
            ],
        )

    def test_a_flow_bazel_builds_partway_names_its_last_stage(self):
        self.assertTrue(
            export_design.next_step(self.dest, self.merged, "place")[1].endswith(
                "config.mk place"
            )
        )

    def test_notes_an_earlier_run_of_the_same_design(self):
        os.makedirs(os.path.join(self.flow, "results", "asap7", "gcd", "base"))
        note = export_design.next_step(self.dest, self.merged, "final")[-1]
        self.assertIn("FLOW_VARIANT=bazel", note)

    def test_outside_orfs(self):
        dest = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
        self.assertEqual(
            export_design.next_step(dest, self.merged, "final"),
            ["next:   make -C <ORFS>/flow DESIGN_CONFIG={}/config.mk".format(dest)],
        )

    def test_writes_only_an_orfs_design(self):
        export_design.write_config(
            self.dest,
            "//pkg:gcd",
            dict(self.merged, CORE_UTILIZATION="65"),
            [],
            "final",
        )
        self.assertEqual(os.listdir(self.dest), ["config.mk"])
        with open(os.path.join(self.dest, "config.mk")) as f:
            text = f.read()
        self.assertTrue(text.startswith(export_design.MARKER))
        self.assertIn("export PLATFORM = asap7\nexport DESIGN_NAME = gcd\n", text)
        self.assertIn("export CORE_UTILIZATION = 65\n", text)

    def test_a_block_finds_the_exports_inputs_above_it(self):
        block = os.path.join(self.dest, "BlockA")
        os.makedirs(block)
        export_design.write_config(
            block,
            "//pkg:BlockA",
            {
                "PLATFORM": "asap7",
                "DESIGN_NAME": "BlockA",
                "DESIGN_NICKNAME": "gcd_BlockA",
                "ABSTRACT_SOURCE": "4_cts",
            },
            [],
            "cts",
            depth=1,
            parent="//pkg:gcd",
        )
        with open(os.path.join(block, "config.mk")) as f:
            text = f.read()
        self.assertIn("One of //pkg:gcd's BLOCKS", text)
        self.assertIn("and abstracts 4_cts.odb", text)
        self.assertIn(
            "export EXPORT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)\n",
            text,
        )

    def test_what_was_made_for_the_export_is_a_default(self):
        export_design.write_config(
            self.dest,
            "//pkg:gcd",
            dict(
                self.merged,
                SYNTH_NETLIST_FILES="$(EXPORT_DIR)/1_2_yosys.v",
                VERILOG_FILES="$(EXPORT_DIR)/inputs/gcd.v",
            ),
            [],
            "final",
            defaults={"SYNTH_NETLIST_FILES"},
        )
        with open(os.path.join(self.dest, "config.mk")) as f:
            text = f.read()
        self.assertIn("export SYNTH_NETLIST_FILES ?= $(EXPORT_DIR)/1_2_yosys.v\n", text)
        self.assertIn("export VERILOG_FILES = $(EXPORT_DIR)/inputs/gcd.v\n", text)
        self.assertIn("make ... SYNTH_NETLIST_FILES=", text)
        self.assertNotIn("MACRO_PLACEMENT_TCL=", text)


if __name__ == "__main__":
    unittest.main()
