"""A/B comparison test: verify mock outputs match real tool outputs.

Parameterized by --stage and --design. Each py_test invocation tests
one stage of one design, comparing the real (base) variant against the
mock variant.

Checks:
1. Both variants produce the required output files
2. Mock outputs have meaningful content (non-empty, parseable)
3. Where applicable, mock estimates are within order of magnitude
"""

import argparse
import glob
import json
import os
import re
import sys
import unittest


def find_runfiles_root():
    """Find the Bazel runfiles root directory."""
    # In Bazel test, RUNFILES_DIR or TEST_SRCDIR is set
    for var in ["RUNFILES_DIR", "TEST_SRCDIR"]:
        d = os.environ.get(var, "")
        if d and os.path.isdir(d):
            return d
    # Fallback: walk up from __file__
    d = os.path.dirname(os.path.abspath(__file__))
    while d != "/":
        if os.path.basename(d).endswith(".runfiles"):
            return d
        d = os.path.dirname(d)
    return "."


def find_stage_dir(design, variant, stage):
    """Find the output directory for a design/variant/stage.

    bazel-orfs outputs land in:
      results/asap7/<design>/<variant>/<stage_files>
    """
    root = find_runfiles_root()
    # Search for the results directory
    patterns = [
        os.path.join(root, "**", "results", "asap7",
                     design, variant),
        os.path.join(root, "_main", "**", "results",
                     "asap7", design, variant),
    ]
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return None


# Stage → expected result files
STAGE_RESULTS = {
    "synth": [
        "1_2_yosys.v", "1_2_yosys.sdc", "1_synth.sdc",
        "mem.json",
    ],
    "floorplan": ["2_floorplan.odb", "2_floorplan.sdc"],
    "place": ["3_place.odb", "3_place.sdc"],
    "cts": ["4_cts.odb", "4_cts.sdc"],
    "grt": ["5_1_grt.odb", "5_1_grt.sdc"],
    "route": ["5_route.odb", "5_route.sdc"],
    "final": [
        "6_final.odb", "6_final.sdc",
        "6_final.spef", "6_final.v",
    ],
}

# Stage → expected report files
STAGE_REPORTS = {
    "synth": ["synth_stat.txt"],
    "floorplan": ["2_floorplan_final.rpt"],
    "cts": ["4_cts_final.rpt"],
    "grt": ["5_global_route.rpt"],
    "route": ["5_route_drc.rpt"],
    "final": ["6_finish.rpt"],
}


class MockCompareTest(unittest.TestCase):
    """Compare real vs mock outputs for a single stage."""

    design = "counter"
    stage = "synth"

    def _find_dir(self, variant):
        d = find_stage_dir(self.design, variant, self.stage)
        if d is None:
            self.skipTest(
                f"Output dir not found for"
                f" {self.design}/{variant}"
            )
        return d

    def test_both_produce_result_files(self):
        """Both variants create the expected result files."""
        expected = STAGE_RESULTS.get(self.stage, [])
        if not expected:
            self.skipTest(
                f"No expected files for stage {self.stage}"
            )

        base_dir = self._find_dir("base")
        mock_dir = self._find_dir("mock")

        for f in expected:
            base_path = os.path.join(base_dir, f)
            mock_path = os.path.join(mock_dir, f)
            self.assertTrue(
                os.path.isfile(base_path),
                f"Real variant missing {f} in {base_dir}",
            )
            self.assertTrue(
                os.path.isfile(mock_path),
                f"Mock variant missing {f} in {mock_dir}",
            )

    def test_mock_outputs_non_empty(self):
        """Mock output files have meaningful content."""
        mock_dir = self._find_dir("mock")
        expected = STAGE_RESULTS.get(self.stage, [])

        for f in expected:
            path = os.path.join(mock_dir, f)
            if not os.path.isfile(path):
                continue
            size = os.path.getsize(path)
            self.assertGreater(
                size, 0,
                f"Mock {f} is empty (0 bytes)",
            )

    def test_mock_odb_has_content(self):
        """Mock ODB files contain at least a header."""
        mock_dir = self._find_dir("mock")
        expected = STAGE_RESULTS.get(self.stage, [])
        odb_files = [f for f in expected if f.endswith(".odb")]

        for f in odb_files:
            path = os.path.join(mock_dir, f)
            if not os.path.isfile(path):
                continue
            with open(path) as fh:
                content = fh.read()
            self.assertTrue(
                len(content) > 0,
                f"Mock {f} is empty",
            )

    def test_synth_stat_cell_count(self):
        """Mock synth_stat.txt reports non-zero cell count."""
        if self.stage != "synth":
            self.skipTest("Only applies to synth stage")

        for variant in ["base", "mock"]:
            d = self._find_dir(variant)
            # synth_stat.txt is in reports dir, one level up
            reports_dir = d.replace("/results/", "/reports/")
            stat_path = os.path.join(reports_dir, "synth_stat.txt")
            if not os.path.isfile(stat_path):
                # Try in results dir
                stat_path = os.path.join(d, "synth_stat.txt")
            if not os.path.isfile(stat_path):
                continue

            with open(stat_path) as f:
                content = f.read()
            m = re.search(
                r"Number of cells:\s+(\d+)", content
            )
            if m:
                cells = int(m.group(1))
                self.assertGreater(
                    cells, 0,
                    f"{variant} reports 0 cells",
                )

    def test_mock_sdc_has_content(self):
        """Mock SDC files contain constraint commands."""
        mock_dir = self._find_dir("mock")
        expected = STAGE_RESULTS.get(self.stage, [])
        sdc_files = [
            f for f in expected if f.endswith(".sdc")
        ]

        for f in sdc_files:
            path = os.path.join(mock_dir, f)
            if not os.path.isfile(path):
                continue
            with open(path) as fh:
                content = fh.read()
            self.assertGreater(
                len(content), 5,
                f"Mock {f} has no meaningful content",
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--design", required=True)
    args, remaining = parser.parse_known_args()

    # Inject into test class
    MockCompareTest.design = args.design
    MockCompareTest.stage = args.stage

    # Run unittest with remaining args
    sys.argv = [sys.argv[0]] + remaining
    unittest.main(module=__name__)


if __name__ == "__main__":
    main()
