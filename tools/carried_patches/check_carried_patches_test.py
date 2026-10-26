import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

import check_carried_patches as ccp

# The shape that actually bit us: two functions whose bodies are identical
# around the line a carried patch keys on.
DUPLICATED_CONTEXT = """\
def estimate_report(name):
    kwargs = {}
    if visibility != None:
        kwargs["visibility"] = visibility
    orfs_run(
        name = name,
    )

def html_report(name):
    kwargs = {}
    if visibility != None:
        kwargs["visibility"] = visibility
    orfs_run(
        name = name,
    )
"""

PATCH = """\
--- a/flow.bzl
+++ b/flow.bzl
@@ -1,3 +1,4 @@
     if visibility != None:
         kwargs["visibility"] = visibility
+    kwargs["tags"] = ["manual"]
     orfs_run(
"""


def _tree(**files):
    return lambda path: files.get(path)


class TestParsePatch(unittest.TestCase):

    def test_splits_context_removals_and_additions(self):
        ((path, pre, post),) = ccp.parse_patch(PATCH)
        self.assertEqual(path, "flow.bzl")
        self.assertNotIn('    kwargs["tags"] = ["manual"]', pre)
        self.assertIn('    kwargs["tags"] = ["manual"]', post)

    def test_multi_file_patch_yields_a_hunk_per_file(self):
        text = (
            "--- a/one.txt\n+++ b/one.txt\n@@ -1,1 +1,1 @@\n-a\n+b\n"
            "--- a/two.txt\n+++ b/two.txt\n@@ -1,1 +1,1 @@\n-c\n+d\n"
        )
        self.assertEqual([h[0] for h in ccp.parse_patch(text)], ["one.txt", "two.txt"])

    def test_a_hunk_ends_where_its_header_says(self):
        """git format-patch's ``-- `` signature is not a removed line."""
        text = (
            "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n keep\n-a\n+b\n" "-- \n2.43.0\n"
        )
        self.assertEqual(
            ccp.parse_patch(text), [("f.txt", ("keep", "a"), ("keep", "b"))]
        )


class TestClassify(unittest.TestCase):

    def test_unique_context_is_clean(self):
        tree = _tree(**{"flow.bzl": "if visibility != None:\n"})
        single = """\
--- a/flow.bzl
+++ b/flow.bzl
@@ -1,1 +1,2 @@
 if visibility != None:
+    tagged = True
"""
        verdict, _ = ccp.classify_patch(single, tree)
        self.assertEqual(verdict, ccp.CLEAN)

    def test_duplicated_context_is_ambiguous(self):
        """The failure mode with no error signal: two candidate sites."""
        verdict, _ = ccp.classify_patch(
            PATCH, _tree(**{"flow.bzl": DUPLICATED_CONTEXT})
        )
        self.assertEqual(verdict, ccp.AMBIGUOUS)

    def test_upstream_absorbed_is_reported_as_absorbed(self):
        absorbed = """\
    if visibility != None:
        kwargs["visibility"] = visibility
    kwargs["tags"] = ["manual"]
    orfs_run(
"""
        verdict, _ = ccp.classify_patch(PATCH, _tree(**{"flow.bzl": absorbed}))
        self.assertEqual(verdict, ccp.ABSORBED)

    def test_absorbed_at_one_site_while_another_still_matches_is_clean(self):
        """One site taking the change does not make the carry redundant."""
        half = DUPLICATED_CONTEXT.replace(
            '        kwargs["visibility"] = visibility\n    orfs_run(',
            '        kwargs["visibility"] = visibility\n'
            '    kwargs["tags"] = ["manual"]\n    orfs_run(',
            1,
        )
        verdict, _ = ccp.classify_patch(PATCH, _tree(**{"flow.bzl": half}))
        self.assertEqual(verdict, ccp.CLEAN)

    def test_moved_code_needs_rebase(self):
        verdict, _ = ccp.classify_patch(PATCH, _tree(**{"flow.bzl": "unrelated\n"}))
        self.assertEqual(verdict, ccp.NEEDS_REBASE)

    def test_missing_target_file_needs_rebase(self):
        verdict, _ = ccp.classify_patch(PATCH, _tree())
        self.assertEqual(verdict, ccp.NEEDS_REBASE)

    def test_worst_hunk_decides_the_patch(self):
        """A patch is only as trustworthy as its least trustworthy hunk."""
        text = (
            "--- a/one.txt\n+++ b/one.txt\n@@ -1,1 +1,2 @@\n unique\n+added\n"
            "--- a/two.txt\n+++ b/two.txt\n@@ -1,1 +1,2 @@\n dup\n+added\n"
        )
        verdict, _ = ccp.classify_patch(
            text, _tree(**{"one.txt": "unique\n", "two.txt": "dup\ndup\n"})
        )
        self.assertEqual(verdict, ccp.AMBIGUOUS)


class TestCountOccurrences(unittest.TestCase):

    def test_counts_every_site(self):
        self.assertEqual(ccp.count_occurrences(["a", "b", "a", "b"], ["a", "b"]), 2)

    def test_empty_needle_matches_nothing(self):
        self.assertEqual(ccp.count_occurrences(["a"], []), 0)


class TestLabels(unittest.TestCase):

    def test_extracts_patch_labels_in_order_without_duplicates(self):
        text = """
            patches = ["//patches:a.patch", "//patches:b.patch"]
            patches = ["//patches:a.patch"]
            urls = ["https://example.com/not-a.patch.tar.gz"]
        """
        self.assertEqual(
            ccp.patch_labels(text),
            ["//patches:a.patch", "//patches:b.patch"],
        )

    def test_finds_a_patch_inlined_into_patch_cmds_by_its_comment(self):
        text = """
            patch_cmds = [
                # Extracted from //patches:sta.patch
                "echo AAAA | base64 -d | patch -p1 || (echo 'rebase //patches:sta.patch.')",
            ],
        """
        self.assertEqual(ccp.patch_labels(text), ["//patches:sta.patch"])

    def test_label_becomes_a_workspace_relative_path(self):
        self.assertEqual(ccp.label_to_path("//patches:foo.patch"), "patches/foo.patch")


MODULE_WITH_TWO_TREES = """\
bazel_dep(name = "openroad")
archive_override(
    module_name = "openroad",
    patches = [
        "//patches:openroad-one.patch",
        "//patches:openroad-two.patch",
    ],
)

orfs.source(
    commit = "abc",
    patches = [
        "//patches:orfs-one.patch",
    ],
)

http_archive(
    name = "pybind11_abseil",
    patches = ["//thirdparty/patches:pybind11.patch"],
)
"""


class PatchGroupsTest(unittest.TestCase):
    """Each carried patch belongs to the dependency whose override lists it."""

    def test_groups_by_module_name_and_tag(self):
        groups = ccp.patch_groups(MODULE_WITH_TWO_TREES)
        self.assertEqual(
            groups["openroad"],
            [
                "//patches:openroad-one.patch",
                "//patches:openroad-two.patch",
            ],
        )
        self.assertEqual(groups["orfs"], ["//patches:orfs-one.patch"])

    def test_http_archive_groups_by_its_name(self):
        groups = ccp.patch_groups(MODULE_WITH_TWO_TREES)
        self.assertEqual(
            groups["pybind11_abseil"], ["//thirdparty/patches:pybind11.patch"]
        )

    def test_a_block_without_patches_makes_no_group(self):
        self.assertEqual(ccp.patch_groups('bazel_dep(name = "x")\n'), {})

    def test_every_patch_lands_in_exactly_one_group(self):
        groups = ccp.patch_groups(MODULE_WITH_TWO_TREES)
        flat = [label for labels in groups.values() for label in labels]
        self.assertEqual(sorted(flat), sorted(ccp.patch_labels(MODULE_WITH_TWO_TREES)))
        self.assertEqual(len(flat), len(set(flat)))


class CreatedFileTest(unittest.TestCase):
    """A patch that adds a file targets a tree that does not have it."""

    CREATE = """\
--- /dev/null
+++ b/src/new_thing.cc
@@ -0,0 +1,2 @@
+int main() {}
+// tail
"""

    MODIFY = """\
--- a/src/gone.cc
+++ b/src/gone.cc
@@ -1,1 +1,2 @@
 int main() {}
+// added
"""

    def test_creating_an_absent_file_is_clean(self):
        verdict, _ = ccp.classify_patch(self.CREATE, lambda path: None)
        self.assertEqual(verdict, ccp.CLEAN)

    def test_modifying_an_absent_file_still_needs_rebase(self):
        verdict, _ = ccp.classify_patch(self.MODIFY, lambda path: None)
        self.assertEqual(verdict, ccp.NEEDS_REBASE)


class TestMain(unittest.TestCase):

    def _run(self, workspace, *argv):
        out = io.StringIO()
        cwd = os.getcwd()
        try:
            with mock.patch.dict(
                os.environ, {"BUILD_WORKSPACE_DIRECTORY": workspace}
            ), contextlib.redirect_stdout(out):
                code = ccp.main(list(argv))
        finally:
            os.chdir(cwd)
        return code, out.getvalue()

    def _workspace(self, root, patch):
        with open(os.path.join(root, "MODULE.bazel"), "w") as f:
            f.write(
                'git_override(\n    module_name = "orfs",\n'
                '    patches = ["//patches:a.patch"],\n)\n'
            )
        if patch is not None:
            os.mkdir(os.path.join(root, "patches"))
            with open(os.path.join(root, "patches", "a.patch"), "w") as f:
                f.write(patch)
        tree = os.path.join(root, "tree")
        os.mkdir(tree)
        with open(os.path.join(tree, "flow.bzl"), "w") as f:
            f.write(DUPLICATED_CONTEXT)
        return tree

    def test_bazel_run_resolves_labels_against_the_workspace(self):
        with tempfile.TemporaryDirectory() as root:
            tree = self._workspace(root, PATCH)
            code, out = self._run(root, "--tree", f"orfs={tree}")
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS", out)

    def test_a_patch_file_that_does_not_exist_fails(self):
        with tempfile.TemporaryDirectory() as root:
            tree = self._workspace(root, None)
            code, out = self._run(root, "--tree", f"orfs={tree}")
        self.assertEqual(code, 1)
        self.assertIn("MISSING", out)

    def test_a_renamed_file_is_checked_and_applied_at_its_old_path(self):
        rename = (
            "diff --git a/old.txt b/new.txt\nsimilarity index 50%\n"
            "rename from old.txt\nrename to new.txt\n"
            "--- a/old.txt\n+++ b/new.txt\n@@ -1,2 +1,2 @@\n"
            " keep\n-one\n+two\n"
        )
        tree = _tree(**{"old.txt": "keep\none\n"})
        self.assertEqual(ccp.classify_patch(rename, tree)[0], ccp.CLEAN)
        overlay = {}
        ccp.apply_patch(rename, lambda p: overlay.get(p, tree(p)), overlay)
        self.assertEqual(overlay, {"new.txt": "keep\ntwo\n", "old.txt": None})

    def test_a_series_is_checked_against_the_tree_its_patches_leave(self):
        first = "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n" " keep\n-one\n+two\n"
        second = "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n" " keep\n-two\n+three\n"
        with tempfile.TemporaryDirectory() as root:
            tree = os.path.join(root, "tree")
            os.mkdir(tree)
            with open(os.path.join(tree, "f.txt"), "w") as f:
                f.write("keep\none\n")
            for name, text in (("1.patch", first), ("2.patch", second)):
                with open(os.path.join(root, name), "w") as f:
                    f.write(text)
            code, out = self._run(
                root, "--tree", tree, "--patch", "1.patch", "--patch", "2.patch"
            )
            self.assertEqual((code, out), (0, ""))
            code, out = self._run(root, "--tree", tree, "--patch", "2.patch")
        self.assertEqual(code, 1)
        self.assertIn("NEEDS_REBASE", out)


if __name__ == "__main__":
    unittest.main()
