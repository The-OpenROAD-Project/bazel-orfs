"""The recorded ORFS design BUILD files.

Most design packages are two lines and orfs_source.bzl generates them.
The other 117 cannot be generated: a `files()` group name is decided by
which label *other* designs' config.mk files reference, not by the
directory's contents. src/cva6 declares files("verilog") while holding no
.v or .sv at all; prim/rtl holds both .sv and .svh but declares
files("include"). Guessing renames a target and the breakage lands in an
unrelated design's config.

So they are carried as data, recorded verbatim by ./record_orfs_builds.py
and written back absent-only. These tests hold the data honest.
"""

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DELIMITER = "ORFS_RECORDED_BUILD_EOF"


def _recorded():
    """RECORDED_BUILDS, read as Starlark-that-is-also-Python."""
    ns = {}
    exec(  # noqa: S102 - our own generated data file
        (_ROOT / "orfs_design_builds.bzl").read_text(),
        ns,
    )
    return ns["RECORDED_BUILDS"], ns["RECORDED_FROM_ORFS"]


def _writer_script(recorded):
    """The same shell _write_recorded_builds() emits, from the same data."""
    parts = []
    for path in sorted(recorded):
        d = path.rsplit("/", 1)[0]
        parts.append(
            "if [ ! -e %s ] && [ ! -e %s/BUILD.bazel ] && [ ! -e %s/BUILD ]; then\n"
            "mkdir -p %s\ncat > %s <<'%s'\n%s%s\nfi\n"
            % (path, d, d, d, path, _DELIMITER, recorded[path], _DELIMITER)
        )
    return "".join(parts)


class TestRecordedData(unittest.TestCase):
    def setUp(self):
        self.recorded, self.commit = _recorded()

    def test_the_expected_number_of_files(self):
        # A sudden change here means ORFS added or removed design
        # packages, or the recorder was run against a dirty tree.
        self.assertEqual(len(self.recorded), 117)

    def test_records_the_orfs_commit_it_came_from(self):
        self.assertRegex(self.commit, r"^[0-9a-f]{40}$")

    def test_no_file_contains_the_heredoc_delimiter(self):
        # The writer would terminate early and produce a truncated BUILD.
        for path, text in self.recorded.items():
            with self.subTest(path=path):
                self.assertNotIn(_DELIMITER, text)

    def test_none_are_the_generated_two_liner(self):
        # Those are produced by orfs_source.bzl's config.mk generator;
        # recording them too would mean two sources of truth.
        for path, text in self.recorded.items():
            lines = [
                l.strip()
                for l in text.splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]
            with self.subTest(path=path):
                self.assertNotEqual(
                    lines,
                    [
                        'load("//flow/designs:design.bzl", "design")',
                        'design(config = "config.mk")',
                    ],
                )

    def test_every_path_is_under_flow_designs(self):
        for path in self.recorded:
            with self.subTest(path=path):
                self.assertTrue(path.startswith("flow/designs/"))
                self.assertIn(os.path.basename(path), ("BUILD", "BUILD.bazel"))

    def test_files_group_names_that_are_not_derivable_are_present(self):
        # The two cases that make derivation impossible. If either
        # disappears, revisit whether recording is still necessary.
        cva6 = self.recorded.get("flow/designs/src/cva6/BUILD", "")
        self.assertIn('files("verilog")', cva6)


class TestWriter(unittest.TestCase):
    def setUp(self):
        self.recorded, _ = _recorded()
        self.script = _writer_script(self.recorded)
        self.tmp = tempfile.mkdtemp()

    def _run(self):
        subprocess.run(["bash", "-c", self.script], cwd=self.tmp, check=True)

    def test_writes_every_file_byte_identically(self):
        self._run()
        for path, want in self.recorded.items():
            with self.subTest(path=path):
                self.assertEqual(
                    pathlib.Path(self.tmp, path).read_text(),
                    want,
                )

    def test_absent_only(self):
        target = pathlib.Path(self.tmp, "flow/designs/src/cva6/BUILD")
        target.parent.mkdir(parents=True)
        target.write_text("# hand written, must survive\n")
        self._run()
        self.assertEqual(target.read_text(), "# hand written, must survive\n")

    def test_bazel_suffixed_name_also_counts_as_present(self):
        d = pathlib.Path(self.tmp, "flow/designs/src/cva6")
        d.mkdir(parents=True)
        (d / "BUILD.bazel").write_text("# hand written\n")
        self._run()
        self.assertFalse((d / "BUILD").exists())

    def test_second_run_is_a_no_op(self):
        self._run()
        first = {p: pathlib.Path(self.tmp, p).read_text() for p in self.recorded}
        self._run()
        for path, text in first.items():
            with self.subTest(path=path):
                self.assertEqual(pathlib.Path(self.tmp, path).read_text(), text)


class TestAgainstARealOrfs(unittest.TestCase):
    """Drift check, when an ORFS checkout is available."""

    def setUp(self):
        self.root = os.environ.get("ORFS_DESIGNS_DIR")
        if not self.root:
            self.skipTest("set ORFS_DESIGNS_DIR to check a real tree")
        self.recorded, _ = _recorded()

    def test_recorded_content_matches_what_orfs_ships(self):
        stale = []
        for path, want in self.recorded.items():
            actual = pathlib.Path(self.root, path)
            if not actual.exists():
                continue  # ORFS has deleted it; that is the goal state
            if actual.read_text() != want:
                stale.append(path)
        self.assertEqual(stale, [], "re-run ./record_orfs_builds.py")


if __name__ == "__main__":
    unittest.main()
