"""The generated flow/BUILD and flow/util/BUILD.

ORFS should not have to carry bazel files for a build system it does not
use, so bazel-orfs generates them when absent -- the same absent-only
rule as the design BUILDs. These two packages are the whole non-design
coupling surface: every `@orfs//` label bazel-orfs resolves comes from
them.

The generator is extracted from orfs_source.bzl and run for real rather
than compared against a copy. Against today's ORFS it writes nothing,
because both files exist, so a future ORFS that has deleted them is
otherwise the only thing exercising it.
"""

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Labels bazel-orfs resolves against @orfs. Anything dropped from the
# generated BUILD files breaks one of these, so they are spelled out
# rather than derived.
_REQUIRED_TARGETS = [
    ("flow/BUILD", "makefile"),
    ("flow/BUILD", "makefile_yosys"),
    ("flow/util/BUILD", "makefile"),
    ("flow/util/BUILD", "makefile_yosys"),
]

_REQUIRED_EXPORTS = [
    # The floorplan derivation compares its duplicated stage sequence
    # against the one that actually runs, so it needs flow.tcl as a
    # label. Patch 0047 adds this to the flow/BUILD ORFS still ships;
    # this list covers the generated one that replaces it.
    "scripts/flow.tcl",
    "scripts/synth.tcl",
    # bazel-orfs's variables_yaml default. ORFS itself does not export
    # this; it resolves today only because load_json_file is a repository
    # rule reading through repository_ctx.path().
    "scripts/variables.yaml",
]

# ORFS's own bazel-only conveniences. Nothing in bazel-orfs consumes
# them and no ORFS workflow invokes bazel, so generating them would mean
# maintaining ORFS's test wiring from the outside. Listed so that adding
# one is a deliberate act rather than a drift.
_DELIBERATELY_ABSENT = [
    "memories",
    "memories_tests",
    "memories_test_fixtures",
    "synDashboard",
    "genMetrics_test",
    "requirements",
]


def _generator_script():
    src = (_ROOT / "orfs_source.bzl").read_text()
    marker = '_GENERATE_FLOW_BUILD = """'
    start = src.index(marker) + len(marker)
    return src[start : src.index('"""', start)]


def _run_generator(tmp, preexisting=()):
    os.makedirs(os.path.join(tmp, "flow", "util"), exist_ok=True)
    for rel in preexisting:
        path = pathlib.Path(tmp, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# hand written, must survive\n")
    result = subprocess.run(
        ["bash", "-c", _generator_script()],
        cwd=tmp,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result


class TestFlowBuildGenerator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _run_generator(self.tmp)
        self.text = {
            rel: pathlib.Path(self.tmp, rel).read_text()
            for rel in ("flow/BUILD", "flow/util/BUILD")
        }

    def _names(self, rel):
        return set(re.findall(r'name = "([^"]+)"', self.text[rel]))

    def test_required_targets_are_declared(self):
        for rel, target in _REQUIRED_TARGETS:
            with self.subTest(label="@orfs//%s:%s" % (rel, target)):
                self.assertIn(target, self._names(rel))

    def test_orfs_pdk_is_declared_for_every_bazel_platform(self):
        # The rule is a comprehension over PDK_EXTS, so assert on that
        # dict rather than on literal target names.
        exts = self.text["flow/BUILD"]
        self.assertIn("orfs_pdk(", exts)
        declared = set(re.findall(r'^    "([a-z0-9-]+)": \[', exts, re.M))
        for platform in (
            "asap7",
            "sky130hd",
            "nangate45",
            "gf180",
            "sky130hs",
            "ihp-sg13g2",
        ):
            with self.subTest(platform=platform):
                self.assertIn(platform, declared)

    def test_platform_files_are_exported(self):
        # config_mk_parser emits per-file labels like
        # //flow:platforms/asap7/lef/... which resolve only via
        # exports_files on the individual files.
        self.assertIn('glob(\n        ["platforms/**/*"]', self.text["flow/BUILD"])

    def test_required_scripts_are_exported(self):
        for name in _REQUIRED_EXPORTS:
            with self.subTest(name=name):
                self.assertIn('"%s",' % name, self.text["flow/BUILD"])

    def test_orfs_own_targets_are_not_reproduced(self):
        declared = self._names("flow/BUILD") | self._names("flow/util/BUILD")
        for name in _DELIBERATELY_ABSENT:
            with self.subTest(name=name):
                self.assertNotIn(name, declared)

    def test_loads_orfs_pdk_from_bazel_orfs(self):
        self.assertIn(
            'load("@bazel-orfs//:openroad.bzl", "orfs_pdk")',
            self.text["flow/BUILD"],
        )


class TestAbsentOnly(unittest.TestCase):
    """A file that exists is never overwritten."""

    def test_existing_flow_build_survives(self):
        tmp = tempfile.mkdtemp()
        _run_generator(tmp, preexisting=["flow/BUILD"])
        self.assertEqual(
            pathlib.Path(tmp, "flow/BUILD").read_text(),
            "# hand written, must survive\n",
        )
        # ... and the other file is still generated.
        self.assertIn("makefile", pathlib.Path(tmp, "flow/util/BUILD").read_text())

    def test_bazel_suffixed_name_also_counts_as_present(self):
        tmp = tempfile.mkdtemp()
        _run_generator(tmp, preexisting=["flow/BUILD.bazel"])
        self.assertFalse(pathlib.Path(tmp, "flow/BUILD").exists())

    def test_second_run_is_a_no_op(self):
        tmp = tempfile.mkdtemp()
        _run_generator(tmp)
        first = pathlib.Path(tmp, "flow/BUILD").read_text()
        _run_generator(tmp)
        self.assertEqual(pathlib.Path(tmp, "flow/BUILD").read_text(), first)


if __name__ == "__main__":
    unittest.main()
