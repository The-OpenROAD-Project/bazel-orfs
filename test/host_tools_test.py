"""Unit tests for the host-tool rules in //:host_tools.

The binary reads the real tree through git; these tests build small
synthetic trees so each rule can be shown to fire and to stay quiet.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import host_tools


def tree(**files):
    """A temporary root holding the given repo-relative files."""
    root = Path(tempfile.mkdtemp())
    for path, content in files.items():
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return root


def check(root):
    return host_tools.check(root, [Path(p) for p in _walk(root)])


def _walk(root):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            yield os.path.relpath(os.path.join(dirpath, name), root)


# A tree with every declared host-python file present and harmless, so a
# test can add exactly the one thing it is about.
def clean_tree(**extra):
    files = {path: "x = 1\n" for path in host_tools.HOST_PYTHON}
    files.update(
        {caller: 'python3 "$X"\n' for caller in host_tools.HOST_PYTHON_CALLERS}
    )
    files.update(extra)
    return tree(**files)


class HostPythonFloorTest(unittest.TestCase):
    def test_clean_tree_has_no_problems(self):
        self.assertEqual(check(clean_tree()), [])

    def test_syntax_above_the_floor_is_a_problem(self):
        root = clean_tree(
            **{"tools/pin/pin.py": "match x:\n    case _:\n        pass\n"}
        )
        problems = check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("tools/pin/pin.py needs python 3.10", problems[0])
        self.assertIn("3.6 on the oldest supported distro", problems[0])

    def test_syntax_at_the_floor_is_fine(self):
        # f-strings are 3.6, the floor itself.
        self.assertEqual(check(clean_tree(**{"bump.py": 'x = f"{1}"\n'})), [])

    def test_a_declared_file_that_vanished_is_a_problem(self):
        files = {path: "x = 1\n" for path in host_tools.HOST_PYTHON}
        del files["bump_impl.py"]
        files.update({c: 'python3 "$X"\n' for c in host_tools.HOST_PYTHON_CALLERS})
        problems = check(tree(**files))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("bump_impl.py is declared as host-run python", problems[0])


class HostPythonCallSiteTest(unittest.TestCase):
    def test_an_undeclared_call_site_is_a_problem(self):
        problems = check(clean_tree(**{"upload.sh": 'python3 "$RUNFILES/upload.py"\n'}))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("upload.sh runs the host python3", problems[0])

    def test_a_call_site_that_went_away_is_a_problem(self):
        root = clean_tree(**{"private/designs.bzl": "# no python here any more\n"})
        problems = check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(
            "private/designs.bzl no longer runs the host python3", problems[0]
        )

    def test_repository_ctx_which_counts_as_a_call_site(self):
        root = clean_tree(**{"fetch.bzl": 'p = repository_ctx.which("python3")\n'})
        problems = check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("fetch.bzl runs the host python3", problems[0])

    def test_test_and_docs_trees_are_not_scanned(self):
        root = clean_tree(
            **{
                "test/helper.sh": 'python3 "$X"\n',
                "docs/example.sh": "jq . foo.json\n",
                "gallery/tmp/run/test.sh": "docker run x\n",
            },
        )
        self.assertEqual(check(root), [])


class DeniedToolTest(unittest.TestCase):
    def test_a_denied_tool_in_a_shipped_script_is_a_problem(self):
        problems = check(clean_tree(**{"report.sh": "jq -r .x foo.json\n"}))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("report.sh runs jq", problems[0])

    def test_a_denied_tool_after_a_pipe_is_a_problem(self):
        problems = check(clean_tree(**{"report.sh": "cat foo.json | jq -r .x\n"}))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("report.sh runs jq", problems[0])

    def test_a_tool_named_in_prose_is_not_a_dependency(self):
        root = clean_tree(
            **{
                "report.sh": (
                    "# docker is not used here\n"
                    'echo "  column -> the second column of the table"\n'
                ),
            },
        )
        self.assertEqual(check(root), [])

    def test_a_longer_name_starting_with_a_denied_tool_is_not_a_match(self):
        self.assertEqual(check(clean_tree(**{"r.sh": "pipefail_helper --x\n"})), [])

    def test_tolerated_tools_are_allowed_only_in_their_own_file(self):
        self.assertEqual(check(clean_tree(**{"open_html.sh": "exec xdg-open x\n"})), [])
        problems = check(clean_tree(**{"other.sh": "exec xdg-open x\n"}))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("other.sh runs xdg-open", problems[0])

    def test_a_denied_tool_in_patch_cmds_is_a_problem(self):
        root = clean_tree(
            **{
                "MODULE.bazel": (
                    "archive_override(\n"
                    '    module_name = "openroad",\n'
                    "    patch_cmds = [\n"
                    '        "wget https://example.com/x.tar.gz",\n'
                    "    ],\n"
                    ")\n"
                ),
            },
        )
        problems = check(root)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("a patch_cmds entry runs wget", problems[0])

    def test_curl_in_patch_cmds_is_allowed(self):
        root = clean_tree(
            **{
                "MODULE.bazel": (
                    "archive_override(\n"
                    "    patch_cmds = [\n"
                    '        "curl -sSfL -o x.tar.gz https://example.com/x.tar.gz",\n'
                    "    ],\n"
                    ")\n"
                ),
            },
        )
        self.assertEqual(check(root), [])


if __name__ == "__main__":
    sys.exit(unittest.main())
