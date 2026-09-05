"""public_surface.py: the dev/non-dev split versus what ships.

Each case builds a small tree in a temp dir and runs check() on it, so
the test is about the rules, not about today's MODULE.bazel; CI runs the
checker on the real tree separately.
"""

import tempfile
import unittest
from pathlib import Path

import public_surface

MODULE = """
module(name = "orfs")

bazel_dep(name = "used", version = "1")
bazel_dep(name = "tagged", version = "1")
bazel_dep(name = "devonly", version = "1", dev_dependency = True)

ext = use_extension("//:ext.bzl", "ext")
ext.default(plugin = "@tagged//:plugin")
use_repo(ext, "gen")

dev_ext = use_extension("//:ext.bzl", "ext", dev_dependency = True)
use_repo(dev_ext, "dev_gen")

designs = use_repo_rule("//:designs.bzl", "designs")

designs(
    name = "designs",
    dev_dependency = True,
)
"""


class Tree:
    def __init__(self, files):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.files = [Path(rel) for rel in files]

    def check(self):
        return public_surface.check(self.root, self.files)


def _tree(extra=None, module=MODULE):
    files = {
        "MODULE.bazel": module,
        "BUILD": 'load("@used//:x.bzl", "x")\n\nx(\n    name = "tool",\n    visibility = ["//visibility:public"],\n)\n',
        # Both reference @used, so a case that replaces one of them keeps
        # the non-dev dep referenced and only exercises what it changes.
        "rules.bzl": 'load("@gen//:g.bzl", "g")\nload("@used//:x.bzl", "x")\n',
    }
    files.update(extra or {})
    return Tree(files)


class PublicSurfaceTest(unittest.TestCase):
    def test_clean_tree_passes(self):
        self.assertEqual(_tree().check(), [])

    def test_public_target_referencing_dev_repo(self):
        t = _tree(
            {
                "BUILD": 'x(\n    name = "tool",\n    data = ["@devonly//:d"],\n    visibility = ["//visibility:public"],\n)\n'
            }
        )
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("BUILD: references @devonly", problems[0])
        self.assertIn("dev-only", problems[0])

    def test_private_target_may_reference_dev_repo(self):
        t = _tree(
            {
                "BUILD": (
                    'x(\n    name = "tool",\n    visibility = ["//visibility:public"],\n)\n\n'
                    'x(\n    name = "lint",\n    data = ["@devonly//:d"],\n)\n'
                )
            }
        )
        self.assertEqual(t.check(), [])

    def test_public_default_visibility_makes_every_target_count(self):
        t = _tree(
            {
                "tools/BUILD": (
                    'package(default_visibility = ["//visibility:public"])\n\n'
                    'x(\n    name = "lint",\n    data = ["@devonly//:d"],\n)\n'
                )
            }
        )
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("tools/BUILD: references @devonly", problems[0])

    def test_load_from_dev_repo_in_shipped_build(self):
        t = _tree(
            {
                "BUILD": (
                    'load("@devonly//:d.bzl", "d")\n\n'
                    'x(\n    name = "tool",\n    visibility = ["//visibility:public"],\n)\n'
                )
            }
        )
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("@devonly", problems[0])

    def test_dev_extension_repo_is_dev(self):
        t = _tree({"rules.bzl": 'load("@dev_gen//:g.bzl", "g")\n'})
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("rules.bzl: references @dev_gen", problems[0])

    def test_dev_repo_rule_is_dev(self):
        t = _tree({"rules.bzl": 'load("@designs//:d.bzl", "d")\n'})
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("@designs", problems[0])

    def test_undeclared_repo_is_reported_as_such(self):
        t = _tree({"rules.bzl": 'load("@nowhere//:n.bzl", "n")\n'})
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("undeclared", problems[0])

    def test_unused_non_dev_bazel_dep(self):
        t = _tree(module=MODULE + '\nbazel_dep(name = "unused", version = "1")\n')
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("bazel_dep 'unused' is non-dev", problems[0])

    def test_bazel_dep_used_only_by_module_tag_counts(self):
        # "tagged" is referenced by nothing but ext.default(plugin = ...).
        self.assertEqual(_tree().check(), [])

    def test_transitive_load_makes_file_shipped(self):
        t = _tree(
            {
                "BUILD": (
                    'load("//tools:t.bzl", "t")\n\n'
                    't(\n    name = "tool",\n    visibility = ["//visibility:public"],\n)\n'
                ),
                "tools/t.bzl": 'load(":inner.bzl", "i")\n',
                "tools/inner.bzl": 'X = "@devonly//:d"\n',
            }
        )
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("tools/inner.bzl: references @devonly", problems[0])

    def test_bzl_beside_public_build_is_shipped(self):
        t = _tree(
            {
                "tools/BUILD": 'x(\n    name = "t",\n    visibility = ["//visibility:public"],\n)\n',
                "tools/api.bzl": 'load("@devonly//:d.bzl", "d")\n',
            }
        )
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("tools/api.bzl", problems[0])

    def test_private_package_is_not_shipped(self):
        t = _tree(
            {
                "examples/BUILD": 'load("@devonly//:d.bzl", "d")\n\nd(name = "e")\n',
                "examples/e.bzl": 'load("@devonly//:d.bzl", "d")\n',
            }
        )
        self.assertEqual(t.check(), [])

    def test_test_dir_is_never_shipped_and_never_public(self):
        t = _tree({"test/BUILD": 'load("@devonly//:d.bzl", "d")\n\nd(name = "t")\n'})
        self.assertEqual(t.check(), [])
        t = _tree(
            {
                "test/BUILD": 'x(\n    name = "t",\n    visibility = ["//visibility:public"],\n)\n'
            }
        )
        problems = t.check()
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("test/BUILD: public target under test/", problems[0])

    def test_bazelignore_and_nested_modules_are_skipped(self):
        t = _tree(
            {
                ".bazelignore": "ignored\n",
                "ignored/BUILD": 'load("@devonly//:d.bzl", "d")\n\nd(\n    name = "i",\n    visibility = ["//visibility:public"],\n)\n',
                "sub/MODULE.bazel": 'module(name = "sub")\n',
                "sub/BUILD": 'load("@devonly//:d.bzl", "d")\n\nd(\n    name = "s",\n    visibility = ["//visibility:public"],\n)\n',
            }
        )
        self.assertEqual(t.check(), [])

    def test_comments_do_not_count(self):
        t = _tree({"rules.bzl": "# see @devonly//:d for the dev-only variant\nX = 1\n"})
        self.assertEqual(t.check(), [])

    def test_allowed_dev_reference(self):
        t = _tree(
            module=MODULE.replace(
                'designs(\n    name = "designs",',
                'designs(\n    name = "orfs_designs",',
            ),
            extra={"orfs_source.bzl": 'X = "@orfs_designs//:designs.bzl"\n'},
        )
        self.assertEqual(t.check(), [])


if __name__ == "__main__":
    unittest.main()
