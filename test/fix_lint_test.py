#!/usr/bin/env python3
"""Unit tests for fix_lint.sh — .bazelignore filtering for mod tidy."""

import os
import subprocess
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")

# The filter_ignored function extracted from fix_lint.sh, plus the
# MODULE_FILES pipeline that must also apply it.
FILTER_SCRIPT = r"""#!/bin/bash
set -e

BAZELIGNORE_PATTERN=""
if [ -f "$1" ]; then
    BAZELIGNORE_PATTERN=$(grep -v '^#' "$1" | grep -v '^$' | sed 's|/$||' | paste -sd'|' | sed 's/|/\\|/g')
fi

filter_ignored() {
    if [ -n "$BAZELIGNORE_PATTERN" ]; then
        grep -v "^\($BAZELIGNORE_PATTERN\)/" || true
    else
        cat
    fi
}

# Read paths from stdin and filter them
cat | filter_ignored
"""


def run_filter(bazelignore_content, input_paths):
    """Run the filter_ignored logic on input_paths given a .bazelignore."""
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".bazelignore", delete=False
    ) as f:
        f.write(bazelignore_content)
        ignore_file = f.name

    try:
        result = subprocess.run(
            ["bash", "-c", FILTER_SCRIPT, "--", ignore_file],
            input="\n".join(input_paths) + "\n" if input_paths else "",
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"filter script failed: {result.stderr}")
        return [l for l in result.stdout.strip().split("\n") if l]
    finally:
        os.unlink(ignore_file)


class TestFilterIgnored(unittest.TestCase):
    """Test that filter_ignored correctly excludes .bazelignore entries."""

    def test_filters_bazelignored_module(self):
        """mock/chisel/MODULE.bazel must be excluded (the CI failure)."""
        ignore = "mock/chisel\ngallery\n"
        paths = [
            "MODULE.bazel",
            "mock/chisel/MODULE.bazel",
            "gallery/MODULE.bazel",
        ]
        result = run_filter(ignore, paths)
        self.assertEqual(result, ["MODULE.bazel"])

    def test_root_module_always_passes(self):
        ignore = "mock/chisel\n"
        result = run_filter(ignore, ["MODULE.bazel"])
        self.assertEqual(result, ["MODULE.bazel"])

    def test_empty_bazelignore(self):
        paths = ["MODULE.bazel", "mock/chisel/MODULE.bazel"]
        result = run_filter("", paths)
        self.assertEqual(result, paths)

    def test_comment_lines_ignored(self):
        ignore = "# this is a comment\nmock/chisel\n"
        paths = ["MODULE.bazel", "mock/chisel/MODULE.bazel"]
        result = run_filter(ignore, paths)
        self.assertEqual(result, ["MODULE.bazel"])

    def test_trailing_slash_stripped(self):
        ignore = "mock/chisel/\n"
        paths = ["mock/chisel/MODULE.bazel"]
        result = run_filter(ignore, paths)
        self.assertEqual(result, [])

    def test_no_input_paths(self):
        result = run_filter("mock/chisel\n", [])
        self.assertEqual(result, [])

    def test_multiple_bazelignore_entries(self):
        ignore = "mock/chisel\nchisel\nsby\ngallery\n"
        paths = [
            "MODULE.bazel",
            "mock/chisel/MODULE.bazel",
            "chisel/MODULE.bazel",
            "sby/MODULE.bazel",
            "gallery/MODULE.bazel",
            "verilog/MODULE.bazel",
        ]
        result = run_filter(ignore, paths)
        self.assertEqual(result, ["MODULE.bazel", "verilog/MODULE.bazel"])


class TestFixLintFilterConsistency(unittest.TestCase):
    """Verify fix_lint.sh applies filter_ignored to MODULE_FILES."""

    def test_module_files_line_includes_filter(self):
        """The MODULE_FILES assignment must pipe through filter_ignored."""
        fix_lint_path = os.path.join(REPO_ROOT, "fix_lint.sh")
        with open(fix_lint_path) as f:
            content = f.read()

        # Find the MODULE_FILES assignment line
        for line in content.splitlines():
            if line.strip().startswith("MODULE_FILES="):
                self.assertIn(
                    "filter_ignored",
                    line,
                    "MODULE_FILES must be piped through filter_ignored "
                    "to respect .bazelignore (see PR #593 CI failure)",
                )
                return

        self.fail("MODULE_FILES assignment not found in fix_lint.sh")


if __name__ == "__main__":
    unittest.main()
