"""Unit tests for gui.query — target parsing and DOT→Cytoscape conversion."""

import unittest

from gui_src.query import parse_dot_to_cytoscape, parse_target


class TestParseTarget(unittest.TestCase):
    def test_simple_target(self):
        result = parse_target("//test:ibex_synth")
        self.assertIsNotNone(result)
        pkg, design, variant, stage = result
        self.assertEqual(pkg, "test")
        self.assertEqual(design, "ibex")
        self.assertEqual(stage, "synth")

    def test_target_with_variant(self):
        result = parse_target("//vlsiffra:multiplier_fast_place")
        self.assertIsNotNone(result)
        pkg, design, variant, stage = result
        self.assertEqual(pkg, "vlsiffra")
        self.assertEqual(design, "multiplier_fast")
        self.assertEqual(stage, "place")

    def test_all_stages(self):
        stages = [
            "synth", "floorplan", "place", "cts", "grt",
            "route", "final", "generate_abstract",
        ]
        for stage in stages:
            result = parse_target(f"//pkg:design_{stage}")
            self.assertIsNotNone(result, f"Failed for stage: {stage}")
            self.assertEqual(result[3], stage)

    def test_non_orfs_target(self):
        result = parse_target("//pkg:some_binary")
        self.assertIsNone(result)

    def test_empty_label(self):
        result = parse_target("")
        self.assertIsNone(result)

    def test_generate_abstract_stage(self):
        result = parse_target("//mem:sram_generate_abstract")
        self.assertIsNotNone(result)
        self.assertEqual(result[1], "sram")
        self.assertEqual(result[3], "generate_abstract")

    def test_nested_package(self):
        result = parse_target("//designs/gemmini:mesh_route")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "designs/gemmini")
        self.assertEqual(result[1], "mesh")
        self.assertEqual(result[3], "route")


class TestParseDotToCytoscape(unittest.TestCase):
    SAMPLE_DOT = """\
digraph mygraph {
  node [shape=box];
  "//test:ibex_synth"
  "//test:ibex_floorplan"
  "//test:ibex_place"
  "//test:ibex_synth" -> "//test:ibex_floorplan"
  "//test:ibex_floorplan" -> "//test:ibex_place"
}
"""

    def test_parses_nodes(self):
        result = parse_dot_to_cytoscape(self.SAMPLE_DOT)
        nodes = result["elements"]["nodes"]
        self.assertEqual(len(nodes), 3)
        ids = {n["data"]["id"] for n in nodes}
        self.assertIn("//test:ibex_synth", ids)
        self.assertIn("//test:ibex_floorplan", ids)
        self.assertIn("//test:ibex_place", ids)

    def test_parses_edges(self):
        result = parse_dot_to_cytoscape(self.SAMPLE_DOT)
        edges = result["elements"]["edges"]
        self.assertEqual(len(edges), 2)

    def test_node_has_stage_and_color(self):
        result = parse_dot_to_cytoscape(self.SAMPLE_DOT)
        nodes = {n["data"]["id"]: n for n in result["elements"]["nodes"]}
        synth = nodes["//test:ibex_synth"]
        self.assertEqual(synth["data"]["stage"], "synth")
        self.assertEqual(synth["data"]["color"], "#6366f1")

    def test_empty_dot(self):
        result = parse_dot_to_cytoscape("")
        self.assertEqual(result["elements"]["nodes"], [])
        self.assertEqual(result["elements"]["edges"], [])

    def test_non_bazel_nodes_ignored(self):
        dot = '"not-a-target" -> "also-not"\n'
        result = parse_dot_to_cytoscape(dot)
        self.assertEqual(result["elements"]["nodes"], [])
        self.assertEqual(result["elements"]["edges"], [])

    def test_edge_creates_missing_nodes(self):
        dot = '"//a:x_synth" -> "//b:y_place"\n'
        result = parse_dot_to_cytoscape(dot)
        self.assertEqual(len(result["elements"]["nodes"]), 2)
        self.assertEqual(len(result["elements"]["edges"]), 1)


if __name__ == "__main__":
    unittest.main()
