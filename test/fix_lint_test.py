#!/usr/bin/env python3
"""Unit tests for fix_lint.py."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import fix_lint


class TestLoadBazelignore(unittest.TestCase):
    def _write(self, content):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".bazelignore", delete=False)
        f.write(content)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_parses_entries(self):
        path = self._write("mock/chisel\ngallery\n")
        self.assertEqual(fix_lint.load_bazelignore(path), {"mock/chisel", "gallery"})

    def test_skips_comments_and_blanks(self):
        path = self._write("# comment\n\nmock/chisel\n")
        self.assertEqual(fix_lint.load_bazelignore(path), {"mock/chisel"})

    def test_strips_trailing_slash(self):
        path = self._write("mock/chisel/\n")
        self.assertEqual(fix_lint.load_bazelignore(path), {"mock/chisel"})

    def test_missing_file_returns_empty(self):
        self.assertEqual(fix_lint.load_bazelignore("/nonexistent"), set())


class TestFilterIgnored(unittest.TestCase):
    def test_filters_bazelignored_paths(self):
        """mock/chisel/MODULE.bazel must be excluded (the CI failure from PR #593)."""
        ignored = {"mock/chisel", "gallery"}
        paths = [
            "MODULE.bazel",
            "mock/chisel/MODULE.bazel",
            "gallery/MODULE.bazel",
        ]
        self.assertEqual(fix_lint.filter_ignored(paths, ignored), ["MODULE.bazel"])

    def test_root_module_always_passes(self):
        self.assertEqual(
            fix_lint.filter_ignored(["MODULE.bazel"], {"mock/chisel"}),
            ["MODULE.bazel"],
        )

    def test_empty_ignored_passes_all(self):
        paths = ["MODULE.bazel", "mock/chisel/MODULE.bazel"]
        self.assertEqual(fix_lint.filter_ignored(paths, set()), paths)

    def test_no_paths(self):
        self.assertEqual(fix_lint.filter_ignored([], {"mock/chisel"}), [])

    def test_multiple_ignored_entries(self):
        ignored = {"mock/chisel", "chisel", "sby", "gallery"}
        paths = [
            "MODULE.bazel",
            "mock/chisel/MODULE.bazel",
            "chisel/MODULE.bazel",
            "sby/MODULE.bazel",
            "gallery/MODULE.bazel",
            "verilog/MODULE.bazel",
        ]
        self.assertEqual(
            fix_lint.filter_ignored(paths, ignored),
            ["MODULE.bazel", "verilog/MODULE.bazel"],
        )

    def test_exact_match_filtered(self):
        """A path equal to an ignored prefix (no trailing /) is also filtered."""
        self.assertEqual(fix_lint.filter_ignored(["chisel"], {"chisel"}), [])

    def test_partial_name_not_filtered(self):
        """'chisel2/foo' must NOT be filtered by 'chisel'."""
        self.assertEqual(
            fix_lint.filter_ignored(["chisel2/foo"], {"chisel"}),
            ["chisel2/foo"],
        )


class TestRunBuildifier(unittest.TestCase):
    @mock.patch("fix_lint.subprocess.call", return_value=0)
    @mock.patch("fix_lint.subprocess.check_call")
    def test_formats_and_lints(self, mock_check_call, mock_call):
        fix_lint.run_buildifier("/path/to/buildifier", ["a.bzl", "BUILD"])
        mock_check_call.assert_called_once_with(
            ["/path/to/buildifier", "a.bzl", "BUILD"]
        )
        mock_call.assert_called_once_with(
            ["/path/to/buildifier", "-lint", "warn", "a.bzl", "BUILD"]
        )

    @mock.patch("fix_lint.subprocess.call", return_value=4)
    @mock.patch("fix_lint.subprocess.check_call")
    def test_lint_warnings_tolerated(self, _mock_check_call, mock_call):
        """Exit code 4 (lint warnings) should not raise."""
        fix_lint.run_buildifier("/path/to/buildifier", ["a.bzl"])
        mock_call.assert_called_once()

    @mock.patch("fix_lint.subprocess.call", return_value=1)
    @mock.patch("fix_lint.subprocess.check_call")
    def test_lint_error_raises(self, _mock_check_call, mock_call):
        """Non-zero exit codes other than 4 should raise."""
        with self.assertRaises(subprocess.CalledProcessError):
            fix_lint.run_buildifier("/path/to/buildifier", ["a.bzl"])

    @mock.patch("fix_lint.subprocess.check_call")
    def test_no_files_is_noop(self, mock_call):
        fix_lint.run_buildifier("/path/to/buildifier", [])
        mock_call.assert_not_called()


class TestRunBlack(unittest.TestCase):
    @mock.patch("fix_lint.shutil.which", return_value="/usr/bin/black")
    @mock.patch("fix_lint.subprocess.check_call")
    def test_formats_python_files(self, mock_call, _which):
        fix_lint.run_black(["a.py", "b.py"])
        mock_call.assert_called_once_with(["black", "--quiet", "a.py", "b.py"])

    @mock.patch("fix_lint.shutil.which", return_value=None)
    @mock.patch("fix_lint.subprocess.check_call")
    def test_skips_when_black_not_found(self, mock_call, _which):
        fix_lint.run_black(["a.py"])
        mock_call.assert_not_called()

    @mock.patch("fix_lint.shutil.which", return_value="/usr/bin/black")
    @mock.patch("fix_lint.subprocess.check_call")
    def test_no_files_is_noop(self, mock_call, _which):
        fix_lint.run_black([])
        mock_call.assert_not_called()


class TestGetMergeBase(unittest.TestCase):
    @mock.patch(
        "fix_lint.subprocess.check_output",
        return_value=b"abc123\n",
    )
    def test_returns_merge_base(self, _):
        self.assertEqual(fix_lint.get_merge_base(), "abc123")

    @mock.patch(
        "fix_lint.subprocess.check_output",
        side_effect=subprocess.CalledProcessError(1, "git"),
    )
    def test_fallback_on_error(self, _):
        self.assertEqual(fix_lint.get_merge_base(), "HEAD~1")


class TestChangedFiles(unittest.TestCase):
    @mock.patch(
        "fix_lint.subprocess.check_output",
        return_value=b"a.bzl\nBUILD\n",
    )
    def test_returns_changed_files(self, _):
        self.assertEqual(
            fix_lint.changed_files("abc", "*.bzl", "BUILD"),
            ["a.bzl", "BUILD"],
        )

    @mock.patch(
        "fix_lint.subprocess.check_output",
        side_effect=subprocess.CalledProcessError(1, "git"),
    )
    def test_returns_empty_on_error(self, _):
        self.assertEqual(fix_lint.changed_files("abc", "*.bzl"), [])


if __name__ == "__main__":
    unittest.main()
