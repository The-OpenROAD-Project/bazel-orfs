#!/usr/bin/env python3
"""Unit tests for bump.py."""

import os
import re
import shutil
import sys
import tempfile
import unittest

# Add repo root to path so we can import bump
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import bump

# Mock values matching the original bash tests
BAZEL_ORFS_COMMIT = "new_bazel_orfs_aaa111"
OPENROAD_COMMIT = "new_openroad_bbb222"
ORFS_COMMIT = "new_orfs_ccc333"
YOSYS_TOOLS_COMMIT = "new_yosys_ddd444"
UPSTREAM_HEAD_COMMIT = "upstream_head_fff666"
MOCK_INTEGRITY = "sha256-MOCKMOCKMOCKMOCKMOCKMOCKMOCKMOCKMOCKMOCKMOCK="

# OpenROAD submodule mocks: SHAs and sha256 hex digests for the two
# submodules the openroad archive_override patch_cmds vendor in
# (src/sta=OpenSTA, third-party/abc=abc, third-party/slang-elab=yosys-slang).
# Real bumps fetch these from GitHub; tests substitute these constants via
# the injection points.
OPENROAD_SUBMODULE_SHAS = {
    "src/sta": "new_opensta_sha_aaaa",
    "third-party/abc": "new_abc_sha_bbbb",
    "third-party/slang-elab": "new_slang_elab_sha_cccc",
}
MOCK_SUB_SHA256_HEX = "deadbeef" * 8  # 64-char hex matches sha256sum -c shape

# ORFS pins tools/yosys to a 0.64-dev commit; BCR has up to 0.63.
MOCK_ORFS_YOSYS_VERSION = (0, 64)
MOCK_BCR_YOSYS_VERSIONS = [
    "0.57",
    "0.57.bcr.3",
    "0.62",
    "0.62.bcr.2",
    "0.63",
]
EXPECTED_YOSYS_BCR_VERSION = "0.63"

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def mock_fetch_commit(repo, branch):
    if "bazel-orfs" in repo:
        return BAZEL_ORFS_COMMIT
    if "OpenROAD-flow-scripts" in repo:
        return ORFS_COMMIT
    # --head=openroad resolves to the tool's upstream HEAD.
    return UPSTREAM_HEAD_COMMIT


def mock_fetch_orfs_tool_sha(_orfs_commit, tool):
    return {
        "yosys": YOSYS_TOOLS_COMMIT,
        "OpenROAD": OPENROAD_COMMIT,
    }[tool]


def mock_fetch_yosys_makefile_version(_sha):
    return MOCK_ORFS_YOSYS_VERSION


def mock_fetch_bcr_versions(_module_name):
    return list(MOCK_BCR_YOSYS_VERSIONS)


def mock_fetch_compare_status_ahead(_repo, _base, _head):
    """Unused since yosys-slang floor-gating was removed; kept for the
    bump() signature the helpers still pass through."""
    return "identical"


def mock_fetch_integrity(_url):
    return MOCK_INTEGRITY


def mock_fetch_sha256_hex(_url):
    return MOCK_SUB_SHA256_HEX


def mock_fetch_submodule_sha(_parent_repo, _parent_commit, path):
    return OPENROAD_SUBMODULE_SHAS[path]


def apply_bump(
    fixture_name,
    workspace_dir=None,
    compare_status_fn=mock_fetch_compare_status_ahead,
    head_tools=None,
):
    """Copy a fixture, run bump on it, return the result content."""
    src = os.path.join(FIXTURES_DIR, fixture_name)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".MODULE.bazel", delete=False)
    tmp.close()
    shutil.copy2(src, tmp.name)

    bump.bump(
        tmp.name,
        fetch_commit_fn=mock_fetch_commit,
        fetch_integrity_fn=mock_fetch_integrity,
        fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
        fetch_compare_status_fn=compare_status_fn,
        fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
        fetch_bcr_versions_fn=mock_fetch_bcr_versions,
        fetch_sha256_hex_fn=mock_fetch_sha256_hex,
        fetch_submodule_sha_fn=mock_fetch_submodule_sha,
        workspace_dir=workspace_dir,
        head_tools=head_tools,
    )

    with open(tmp.name) as f:
        content = f.read()
    os.unlink(tmp.name)
    return content


class TestBazelOrfsProject(unittest.TestCase):
    """Test 1: bazel-orfs project (self)."""

    def setUp(self):
        self.content = apply_bump("self.MODULE.bazel")

    def test_openroad_commit_updated(self):
        self.assertIn(OPENROAD_COMMIT, self.content)

    def test_orfs_commit_updated(self):
        self.assertIn(ORFS_COMMIT, self.content)

    def test_old_orfs_commit_replaced(self):
        self.assertNotIn("old_orfs_commit", self.content)

    def test_bazel_orfs_commit_not_updated(self):
        self.assertNotIn(
            BAZEL_ORFS_COMMIT,
            self.content,
            "bazel-orfs should not update its own commit",
        )


class TestOpenroadProject(unittest.TestCase):
    """Test 2: OpenROAD project (uses variable-reference commit pattern)."""

    def setUp(self):
        self.content = apply_bump("openroad.MODULE.bazel")

    def test_bazel_orfs_commit_variable_updated(self):
        self.assertIn(f'BAZEL_ORFS_COMMIT = "{BAZEL_ORFS_COMMIT}"', self.content)

    def test_old_commit_removed(self):
        self.assertNotIn("old_bazel_orfs_commit", self.content)

    def test_variable_reference_preserved(self):
        """git_override blocks should still use the variable, not inline the value."""
        self.assertIn("commit = BAZEL_ORFS_COMMIT,", self.content)

    def test_openroad_commit_not_updated(self):
        self.assertNotIn(
            OPENROAD_COMMIT, self.content, "OpenROAD should not update its own commit"
        )

    def test_openroad_label_preserved(self):
        self.assertIn('openroad = "//:openroad"', self.content)

    def test_verilog_submodule_uses_same_variable(self):
        """Pre-existing git_override blocks should reference the same variable."""
        for name in ["bazel-orfs", "bazel-orfs-verilog"]:
            block = re.search(
                rf'git_override\(\s*module_name\s*=\s*"{name}".*?\)',
                self.content,
                re.DOTALL,
            )
            self.assertIsNotNone(block, f"{name} block not found")
            self.assertIn("BAZEL_ORFS_COMMIT", block.group())


class TestDownstreamFresh(unittest.TestCase):
    """Test 3: downstream project."""

    def setUp(self):
        self.content = apply_bump("downstream.MODULE.bazel")

    def test_bazel_orfs_commit_updated(self):
        self.assertIn(BAZEL_ORFS_COMMIT, self.content)


class TestDownstreamWithSubmodules(unittest.TestCase):
    """Test: downstream with bazel-orfs-verilog submodule."""

    def setUp(self):
        self.content = apply_bump("downstream-with-submodules.MODULE.bazel")

    def test_bazel_orfs_commit_updated(self):
        self.assertNotIn("old_bazel_orfs_commit", self.content)

    def test_verilog_submodule_commit_updated(self):
        self.assertNotIn("old_verilog_commit", self.content)

    def test_all_submodules_share_same_commit(self):
        """All bazel-orfs submodule overrides should use the same commit."""
        blocks = re.findall(
            r'git_override\(.*?module_name\s*=\s*"(bazel-orfs[^"]*)".*?'
            r'commit\s*=\s*"([^"]*)".*?\)',
            self.content,
            re.DOTALL,
        )
        commits = {name: commit for name, commit in blocks}
        self.assertEqual(commits["bazel-orfs"], BAZEL_ORFS_COMMIT)
        self.assertEqual(commits["bazel-orfs-verilog"], BAZEL_ORFS_COMMIT)

    def test_strip_prefix_preserved(self):
        self.assertIn('strip_prefix = "verilog"', self.content)


def _apply_bump_with_workspace(
    fixture_name,
    build_files,
    compare_status_fn=mock_fetch_compare_status_ahead,
    head_tools=None,
):
    """Copy a fixture into a temp workspace with the given BUILD files.

    build_files is a dict of relpath -> content.  Returns (MODULE.bazel
    content, workspace dir).  Caller is responsible for cleanup if it
    needs to read more files; this helper cleans up only on the no-need
    paths via the simpler `_apply_bump_in_workspace` below.
    """
    tmpdir = tempfile.mkdtemp()
    try:
        src = os.path.join(FIXTURES_DIR, fixture_name)
        module_file = os.path.join(tmpdir, "MODULE.bazel")
        shutil.copy2(src, module_file)
        for relpath, content in build_files.items():
            fpath = os.path.join(tmpdir, relpath)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, "w") as f:
                f.write(content)
        bump.bump(
            module_file,
            fetch_commit_fn=mock_fetch_commit,
            fetch_integrity_fn=mock_fetch_integrity,
            fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
            fetch_compare_status_fn=compare_status_fn,
            fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
            fetch_bcr_versions_fn=mock_fetch_bcr_versions,
            fetch_sha256_hex_fn=mock_fetch_sha256_hex,
            fetch_submodule_sha_fn=mock_fetch_submodule_sha,
            workspace_dir=tmpdir,
            head_tools=head_tools,
        )
        with open(module_file) as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir)


class TestDownstreamSubmodulesInjectedWhenUsed(unittest.TestCase):
    """Submodules that the workspace references should be injected."""

    def test_verilog_injected_when_referenced(self):
        content = _apply_bump_with_workspace(
            "downstream.MODULE.bazel",
            {
                "hw/BUILD.bazel": 'load("@bazel-orfs-verilog//:defs.bzl", "verilog_library")\n'
            },
        )
        self.assertIn('bazel_dep(name = "bazel-orfs-verilog")', content)


class TestDownstreamSubmodulesNotInjectedWhenUnused(unittest.TestCase):
    """Submodules the workspace does not reference should be skipped."""

    def test_no_injection_for_empty_workspace(self):
        content = _apply_bump_with_workspace(
            "downstream.MODULE.bazel",
            {"hw/BUILD.bazel": 'load("@bazel_skylib//lib:paths.bzl", "paths")\n'},
        )
        self.assertNotIn('bazel_dep(name = "bazel-orfs-verilog")', content)


class TestSubmoduleIsUsed(unittest.TestCase):
    """Unit tests for submodule_is_used()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, relpath, content):
        fpath = os.path.join(self.tmpdir, relpath)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w") as f:
            f.write(content)

    def test_detects_direct_repo_ref(self):
        self._write(
            "BUILD.bazel",
            'cc_library(deps = ["@bazel-orfs-verilog//:foo"])\n',
        )
        self.assertTrue(bump.submodule_is_used("bazel-orfs-verilog", self.tmpdir))

    def test_ignores_non_build_files(self):
        self._write("README.md", "See @bazel-orfs-verilog// for details\n")
        self.assertFalse(bump.submodule_is_used("bazel-orfs-verilog", self.tmpdir))

    def test_skips_bazel_output_dirs(self):
        self._write(
            "bazel-bin/BUILD.bazel",
            'load("@bazel-orfs-verilog//:defs.bzl", "verilog_library")\n',
        )
        self.assertFalse(bump.submodule_is_used("bazel-orfs-verilog", self.tmpdir))

    def test_skips_hidden_dirs(self):
        self._write(
            ".git/BUILD.bazel",
            'load("@bazel-orfs-verilog//:defs.bzl", "verilog_library")\n',
        )
        self.assertFalse(bump.submodule_is_used("bazel-orfs-verilog", self.tmpdir))

    def test_not_used_when_no_match(self):
        self._write("BUILD.bazel", 'cc_library(name = "foo")\n')
        self.assertFalse(bump.submodule_is_used("bazel-orfs-verilog", self.tmpdir))


class TestFindBazelOrfsSubmodules(unittest.TestCase):
    def test_finds_present_submodules(self):
        content = (
            'git_override(\n    module_name = "bazel-orfs-verilog",\n'
            '    commit = "abc",\n)\n'
        )
        self.assertEqual(
            bump.find_bazel_orfs_submodules(content),
            ["bazel-orfs-verilog"],
        )

    def test_empty_when_none_present(self):
        content = (
            'git_override(\n    module_name = "bazel-orfs",\n    commit = "x",\n)\n'
        )
        self.assertEqual(bump.find_bazel_orfs_submodules(content), [])


class TestDetectProject(unittest.TestCase):
    def test_bazel_orfs(self):
        content = 'module(\n    name = "bazel-orfs",\n)'
        self.assertEqual(bump.detect_project(content), "bazel-orfs")

    def test_openroad(self):
        content = 'module(\n    name = "openroad",\n)'
        self.assertEqual(bump.detect_project(content), "openroad")

    def test_downstream(self):
        content = 'module(\n    name = "my-chip",\n)'
        self.assertEqual(bump.detect_project(content), "downstream")

    def test_no_module(self):
        self.assertEqual(bump.detect_project("# empty"), "downstream")

    def test_module_with_version(self):
        content = 'module(\n    name = "bazel-orfs",\n    version = "1.0",\n)'
        self.assertEqual(bump.detect_project(content), "bazel-orfs")

    def test_module_single_line(self):
        content = 'module(name = "openroad")'
        self.assertEqual(bump.detect_project(content), "openroad")


class TestUpdateGitOverride(unittest.TestCase):
    def test_updates_matching_block(self):
        content = (
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            '    commit = "old_commit",\n'
            '    remote = "https://...",\n'
            ")"
        )
        result = bump.update_git_override_commit(content, "bazel-orfs", "new_commit")
        self.assertIn('commit = "new_commit"', result)

    def test_does_not_update_other_block(self):
        content = (
            "git_override(\n"
            '    module_name = "other",\n'
            '    commit = "keep_this",\n'
            ")"
        )
        result = bump.update_git_override_commit(content, "bazel-orfs", "new_commit")
        self.assertIn('commit = "keep_this"', result)

    def test_updates_commented_block(self):
        content = (
            "# git_override(\n"
            '#     module_name = "openroad",\n'
            '#     commit = "old_commit",\n'
            "# )"
        )
        result = bump.update_git_override_commit(content, "openroad", "new_commit")
        self.assertIn('commit = "new_commit"', result)

    def test_multiple_blocks_only_target_updated(self):
        content = (
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            '    commit = "aaa",\n'
            ")\n"
            "git_override(\n"
            '    module_name = "bazel-orfs-verilog",\n'
            '    commit = "bbb",\n'
            '    strip_prefix = "verilog",\n'
            ")\n"
        )
        result = bump.update_git_override_commit(content, "bazel-orfs-verilog", "new")
        self.assertIn('commit = "aaa"', result)
        self.assertIn('commit = "new"', result)
        self.assertIn('strip_prefix = "verilog"', result)

    def test_variable_reference_updates_assignment(self):
        content = (
            'MY_COMMIT = "old_commit"\n'
            "\n"
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            "    commit = MY_COMMIT,\n"
            '    remote = "https://...",\n'
            ")"
        )
        result = bump.update_git_override_commit(content, "bazel-orfs", "new_commit")
        self.assertIn('MY_COMMIT = "new_commit"', result)
        self.assertIn("commit = MY_COMMIT,", result)

    def test_variable_reference_shared_by_multiple_blocks(self):
        content = (
            'SHARED = "old"\n'
            "\n"
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            "    commit = SHARED,\n"
            ")\n"
            "git_override(\n"
            '    module_name = "bazel-orfs-verilog",\n'
            "    commit = SHARED,\n"
            '    strip_prefix = "verilog",\n'
            ")"
        )
        result = bump.update_git_override_commit(content, "bazel-orfs", "new")
        self.assertIn('SHARED = "new"', result)
        # Second block still uses the variable (updated via separate call or shared var)
        self.assertIn("commit = SHARED,", result)

    def test_variable_reference_does_not_touch_other_module(self):
        content = (
            'A_COMMIT = "aaa"\n'
            'B_COMMIT = "bbb"\n'
            "\n"
            "git_override(\n"
            '    module_name = "mod-a",\n'
            "    commit = A_COMMIT,\n"
            ")\n"
            "git_override(\n"
            '    module_name = "mod-b",\n'
            "    commit = B_COMMIT,\n"
            ")"
        )
        result = bump.update_git_override_commit(content, "mod-a", "new")
        self.assertIn('A_COMMIT = "new"', result)
        self.assertIn('B_COMMIT = "bbb"', result)

    def test_no_matching_block_is_noop(self):
        content = (
            "git_override(\n"
            '    module_name = "other",\n'
            '    commit = "keep",\n'
            ")"
        )
        result = bump.update_git_override_commit(content, "bazel-orfs", "new")
        self.assertEqual(result, content)

    def test_preserves_other_fields_in_block(self):
        content = (
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            '    commit = "old",\n'
            "    init_submodules = True,\n"
            '    remote = "https://github.com/...",\n'
            ")"
        )
        result = bump.update_git_override_commit(content, "bazel-orfs", "new")
        self.assertIn("init_submodules = True", result)
        self.assertIn("remote =", result)


class TestBazelOrfsSkipsSelfCommit(unittest.TestCase):
    """bazel-orfs project must not update its own git_override commit."""

    def setUp(self):
        self.content = apply_bump("self.MODULE.bazel")

    def test_orfs_commit_updated(self):
        self.assertIn(
            ORFS_COMMIT, self.content, "ORFS commit should be updated for bazel-orfs"
        )


class TestOpenroadSkipsSelfCommit(unittest.TestCase):
    """OpenROAD project must not update its own commit."""

    def setUp(self):
        self.content = apply_bump("openroad.MODULE.bazel")

    def test_does_not_self_update(self):
        self.assertNotIn(
            OPENROAD_COMMIT, self.content, "OpenROAD must not bump its own commit"
        )

    def test_updates_bazel_orfs(self):
        self.assertIn(f'BAZEL_ORFS_COMMIT = "{BAZEL_ORFS_COMMIT}"', self.content)


class TestSubmodulesDoubleUpdate(unittest.TestCase):
    """Bumping a file with submodules twice should be idempotent."""

    def test_double_bump_idempotent(self):
        src = os.path.join(FIXTURES_DIR, "downstream-with-submodules.MODULE.bazel")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".MODULE.bazel", delete=False
        )
        tmp.close()
        shutil.copy2(src, tmp.name)

        kwargs = dict(
            fetch_commit_fn=mock_fetch_commit,
            fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
            fetch_compare_status_fn=mock_fetch_compare_status_ahead,
            fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
            fetch_bcr_versions_fn=mock_fetch_bcr_versions,
        )
        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            first = f.read()

        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            second = f.read()

        os.unlink(tmp.name)
        self.assertEqual(first, second, "Second bump should produce identical output")


class TestNetworkErrorHandling(unittest.TestCase):
    """Test 7: verify clear error messages on failures."""

    def test_commit_fetch_failure(self):
        def bad_commit(_repo, _branch):
            raise RuntimeError("API error")

        with self.assertRaises(RuntimeError):
            src = os.path.join(FIXTURES_DIR, "self.MODULE.bazel")
            tmp = tempfile.NamedTemporaryFile(suffix=".MODULE.bazel", delete=False)
            tmp.close()
            shutil.copy2(src, tmp.name)
            try:
                bump.bump(
                    tmp.name,
                    fetch_commit_fn=bad_commit,
                    fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
                    fetch_compare_status_fn=mock_fetch_compare_status_ahead,
                    fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
                    fetch_bcr_versions_fn=mock_fetch_bcr_versions,
                )
            finally:
                os.unlink(tmp.name)


class TestBazelOrfsArchiveOverride(unittest.TestCase):
    """bazel-orfs project bumping ORFS pinned via archive_override.

    Mirrors TestBazelOrfsProject but expects archive_override-shape rewrites:
    urls, integrity, and strip_prefix all change; patches stay put.
    """

    def setUp(self):
        self.content = apply_bump("self-archive.MODULE.bazel")

    def test_urls_contain_new_commit(self):
        expected_url = (
            "https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/"
            f"archive/{ORFS_COMMIT}.tar.gz"
        )
        self.assertIn(expected_url, self.content)

    def test_old_url_replaced(self):
        self.assertNotIn("old_orfs_commit.tar.gz", self.content)

    def test_integrity_updated(self):
        self.assertIn(f'integrity = "{MOCK_INTEGRITY}"', self.content)
        self.assertNotIn("OLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDA=", self.content)

    def test_strip_prefix_updated(self):
        self.assertIn(
            f'strip_prefix = "OpenROAD-flow-scripts-{ORFS_COMMIT}"',
            self.content,
        )
        self.assertNotIn(
            'strip_prefix = "OpenROAD-flow-scripts-old_orfs_commit"',
            self.content,
        )

    def test_patches_preserved(self):
        self.assertIn(
            "//patches:0036-fix-bazel-orfs-bazel_dep-non-dev-for-load-visibility.patch",
            self.content,
        )
        self.assertIn("patch_strip = 1", self.content)

    def test_openroad_git_override_still_updated(self):
        """Switching ORFS to archive_override mustn't disturb other modules."""
        self.assertIn(OPENROAD_COMMIT, self.content)
        self.assertNotIn("old_openroad_commit", self.content)


class TestArchiveOverrideDoubleBumpIdempotent(unittest.TestCase):
    """Two bumps in a row must produce identical output."""

    def test_double_bump_idempotent(self):
        src = os.path.join(FIXTURES_DIR, "self-archive.MODULE.bazel")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".MODULE.bazel", delete=False
        )
        tmp.close()
        shutil.copy2(src, tmp.name)

        kwargs = dict(
            fetch_commit_fn=mock_fetch_commit,
            fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
            fetch_compare_status_fn=mock_fetch_compare_status_ahead,
            fetch_integrity_fn=mock_fetch_integrity,
            fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
            fetch_bcr_versions_fn=mock_fetch_bcr_versions,
            fetch_sha256_hex_fn=mock_fetch_sha256_hex,
            fetch_submodule_sha_fn=mock_fetch_submodule_sha,
        )
        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            first = f.read()

        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            second = f.read()

        os.unlink(tmp.name)
        self.assertEqual(first, second)


class TestUpdateArchiveOverride(unittest.TestCase):
    """Unit tests for the archive_override block rewriter."""

    def _block(self, **overrides):
        defaults = dict(
            url="https://github.com/Owner/Repo/archive/oldsha.tar.gz",
            integrity="sha256-OLD=",
            strip_prefix="Repo-oldsha",
        )
        defaults.update(overrides)
        return (
            "archive_override(\n"
            '    module_name = "orfs",\n'
            f'    urls = ["{defaults["url"]}"],\n'
            f'    integrity = "{defaults["integrity"]}",\n'
            f'    strip_prefix = "{defaults["strip_prefix"]}",\n'
            ")"
        )

    def test_rewrites_url_integrity_strip_prefix(self):
        result = bump.update_archive_override(
            self._block(),
            "orfs",
            "Owner/Repo",
            "newsha",
            "sha256-NEW=",
        )
        self.assertIn(
            'urls = ["https://github.com/Owner/Repo/archive/newsha.tar.gz"]', result
        )
        self.assertIn('integrity = "sha256-NEW="', result)
        self.assertIn('strip_prefix = "Repo-newsha"', result)

    def test_no_match_is_noop(self):
        content = (
            "archive_override(\n"
            '    module_name = "other",\n'
            '    urls = ["https://example/x.tar.gz"],\n'
            '    integrity = "sha256-X=",\n'
            '    strip_prefix = "x",\n'
            ")"
        )
        result = bump.update_archive_override(
            content, "orfs", "Owner/Repo", "newsha", "sha256-NEW="
        )
        self.assertEqual(result, content)

    def test_other_modules_block_untouched(self):
        content = (
            "archive_override(\n"
            '    module_name = "other",\n'
            '    urls = ["https://example/x.tar.gz"],\n'
            '    integrity = "sha256-X=",\n'
            '    strip_prefix = "x",\n'
            ")\n" + self._block()
        )
        result = bump.update_archive_override(
            content, "orfs", "Owner/Repo", "newsha", "sha256-NEW="
        )
        self.assertIn('integrity = "sha256-X="', result)
        self.assertIn("https://example/x.tar.gz", result)
        self.assertIn(
            'urls = ["https://github.com/Owner/Repo/archive/newsha.tar.gz"]', result
        )


class TestFindArchiveOverrideBlock(unittest.TestCase):
    def test_finds_block(self):
        content = (
            "archive_override(\n"
            '    module_name = "orfs",\n'
            '    urls = ["https://example/x.tar.gz"],\n'
            ")"
        )
        span = bump.find_archive_override_block(content, "orfs")
        self.assertIsNotNone(span)
        self.assertIn("orfs", content[span[0] : span[1]])

    def test_returns_none_when_absent(self):
        content = 'git_override(\n    module_name = "orfs",\n    commit = "x",\n)'
        self.assertIsNone(bump.find_archive_override_block(content, "orfs"))

    def test_ignores_match_inside_comment_before_real_block(self):
        # A prose comment that wraps an ``archive_override(`` mention across
        # lines — opening paren on one comment line, closing paren on a
        # *subsequent* comment line — is the realistic shape this guard
        # protects against.  ``find_starlark_call_end`` skips comment-line
        # interiors when it encounters ``#``, so the closing ``)`` on the
        # next comment line is silently consumed; without the comment
        # filter on ``re.finditer`` matches, the scan would then walk on,
        # increment depth at the real ``archive_override(`` below, and only
        # exit at some later stray ``)`` — wrapping the real block (and
        # everything between) inside one runaway "block" that the rewriter
        # then either no-ops or corrupts.
        content = (
            "# Pinned via archive_override (GitHub /archive/<sha>.tar.gz +\n"
            "# patch_cmds for submodules) rather than git_override +\n"
            "# init_submodules — the latter has a non-atomic-fetch bug.\n"
            "archive_override(\n"
            '    module_name = "orfs",\n'
            '    urls = ["https://example/x.tar.gz"],\n'
            ")"
        )
        span = bump.find_archive_override_block(content, "orfs")
        self.assertIsNotNone(span)
        block = content[span[0] : span[1]]
        self.assertTrue(block.startswith("archive_override("))
        self.assertTrue(block.endswith(")"))
        self.assertNotIn("Pinned via", block)
        self.assertNotIn("# patch_cmds for submodules", block)

    def test_ignores_match_in_indented_comment(self):
        # Comments aren't always at column 0 — buildifier preserves leading
        # whitespace before ``#``.  Indented prose with an unbalanced ``(``
        # on the same line as the call mention must still be skipped.
        comment = (
            "    # see archive_override( above for the parent pin;\n"
            "    # the close-paren is on this trailing comment line ).\n"
        )
        active = 'archive_override(\n    module_name = "orfs",\n)'
        content = comment + active
        span = bump.find_archive_override_block(content, "orfs")
        self.assertIsNotNone(span)
        # The span must start at the active block, not at the comment.
        self.assertEqual(span[0], len(comment))
        block = content[span[0] : span[1]]
        self.assertEqual(block, active)

    def test_only_commented_block_returns_none(self):
        # If every occurrence is inside a comment, the finder must return
        # None.  Returning a runaway span (or a bogus in-comment span) would
        # make ``update_openroad_archive_override`` either rewrite the
        # comment in place or corrupt unrelated code below it.
        content = (
            "# archive_override(\n"
            '#     module_name = "orfs",\n'
            "# )\n"
            'git_override(\n    module_name = "other",\n    commit = "x",\n)'
        )
        self.assertIsNone(bump.find_archive_override_block(content, "orfs"))


class TestFindGitOverrideBlock(unittest.TestCase):
    def test_ignores_match_inside_comment_before_real_block(self):
        # Same hazard as the archive_override case: a commented-out
        # ``# git_override(`` ahead of the real block must be skipped so the
        # finder doesn't return a span that begins inside the comment.
        content = (
            "# Worker-wrapper fork — swap the git_override( above to enable.\n"
            "# git_override(\n"
            '#     module_name = "bazel-orfs",\n'
            '#     commit = "old",\n'
            "# )\n"
            "\n"
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            '    commit = "real",\n'
            ")"
        )
        span = bump.find_git_override_block(content, "bazel-orfs")
        self.assertIsNotNone(span)
        block = content[span[0] : span[1]]
        self.assertTrue(block.startswith("git_override("))
        self.assertIn('commit = "real"', block)
        self.assertNotIn("Worker-wrapper", block)
        self.assertNotIn('commit = "old"', block)

    def test_only_commented_block_returns_none(self):
        content = (
            "# git_override(\n"
            '#     module_name = "bazel-orfs",\n'
            '#     commit = "old",\n'
            "# )\n"
        )
        self.assertIsNone(bump.find_git_override_block(content, "bazel-orfs"))


class TestUpdateOpenroadArchiveOverrideAroundComments(unittest.TestCase):
    """Regression: comments mentioning ``archive_override(`` next to the
    real block must not derail the openroad rewriter.

    The original bug: a downstream MODULE.bazel with a leading prose
    comment ``# Pinned via archive_override (...)`` caused
    ``find_archive_override_block`` to match inside the comment.
    ``find_starlark_call_end`` then walked from the ``#`` line into the
    real block and beyond, returning a runaway span.  The rewriter then
    either no-oped (because depth tracking landed at the wrong ``)``) or
    corrupted everything between the comment and the next stray ``)`` in
    the file.
    """

    def test_rewrite_targets_active_block_not_comment(self):
        # Realistic comment shape: ``(`` on one comment line, ``)`` on a
        # later one — Starlark-call-end skips the inner ``#`` lines, so the
        # unbalanced ``(`` in the comment used to leak into the real block
        # below and produce a runaway span.
        content = (
            "# Pinned via archive_override (GitHub /archive/<sha>.tar.gz +\n"
            "# patch_cmds for submodules) so the submodule-fetch race in\n"
            "# git_override + init_submodules can't strand us.\n"
            "archive_override(\n"
            '    module_name = "openroad",\n'
            '    integrity = "sha256-OLD=",\n'
            "    patches = [],\n"
            '    strip_prefix = "OpenROAD-old_openroad_commit",\n'
            '    urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/old_openroad_commit.tar.gz"],\n'
            ")\n"
        )

        def fake_int(_url):
            return "sha256-NEW="

        def fake_hex(_url):
            return "f" * 64

        def fake_sub(_repo, _commit, path):
            return OPENROAD_SUBMODULE_SHAS[path]

        new_content = bump.update_openroad_archive_override(
            content,
            "new_openroad_commit",
            fetch_integrity_fn=fake_int,
            fetch_sha256_hex_fn=fake_hex,
            fetch_submodule_sha_fn=fake_sub,
        )
        # The active block was actually rewritten — old SHA is gone.
        self.assertNotIn("old_openroad_commit", new_content)
        self.assertIn('strip_prefix = "OpenROAD-new_openroad_commit"', new_content)
        self.assertIn("new_openroad_commit.tar.gz", new_content)
        # And the comment block is intact (not consumed by a runaway span).
        self.assertIn("# Pinned via archive_override (GitHub", new_content)
        self.assertIn(
            "# patch_cmds for submodules) so the submodule-fetch race",
            new_content,
        )


class TestDownstreamOrfsToolsFlow(unittest.TestCase):
    """Downstream: openroad commit and yosys BCR version follow ORFS tools/."""

    def setUp(self):
        self.content = apply_bump("downstream.MODULE.bazel")

    def test_orfs_commit_updated(self):
        # New: downstream bumps ORFS too (used to be bazel-orfs-project only).
        self.assertIn(ORFS_COMMIT, self.content)
        self.assertNotIn("old_orfs_commit", self.content)

    def test_yosys_bcr_version_bumped(self):
        # ORFS pins yosys to YOSYS_VER 0.64; latest BCR <= 0.64 is 0.63.
        self.assertIn(
            f'bazel_dep(name = "yosys", version = "{EXPECTED_YOSYS_BCR_VERSION}")',
            self.content,
        )
        # No git_override block should be written for yosys.
        self.assertNotIn('module_name = "yosys"', self.content)

    def test_openroad_pinned_to_orfs_tools_sha(self):
        self.assertIn(OPENROAD_COMMIT, self.content)
        self.assertNotIn("old_openroad_commit", self.content)


class TestHeadFlagOverrides(unittest.TestCase):
    """--head=openroad bypasses the ORFS-tools sha, using the tool's own HEAD."""

    def test_head_openroad_uses_upstream_head(self):
        # openroad is pinned via archive_override (not git_override) after the
        # switch to fix submodule-fetch races — see OPENROAD_REPO in bump.py.
        content = apply_bump(
            "downstream.MODULE.bazel",
            head_tools={"openroad"},
        )
        span = bump.find_archive_override_block(content, "openroad")
        self.assertIsNotNone(span)
        block = content[span[0] : span[1]]
        self.assertIn(UPSTREAM_HEAD_COMMIT, block)
        self.assertNotIn(OPENROAD_COMMIT, block)


class TestPickBcrYosysVersion(unittest.TestCase):
    """Unit tests for pick_bcr_yosys_version()."""

    BCR = ["0.57", "0.57.bcr.3", "0.62", "0.62.bcr.1", "0.62.bcr.2", "0.63"]

    def test_picks_highest_at_or_below_target(self):
        # ORFS pins YOSYS_VER 0.64; latest BCR <= 0.64 is 0.63.
        self.assertEqual(bump.pick_bcr_yosys_version(self.BCR, (0, 64)), "0.63")

    def test_exact_match_prefers_highest_bcr_variant(self):
        # ORFS pins 0.62; 0.62.bcr.2 outranks 0.62.bcr.1 and bare 0.62.
        self.assertEqual(bump.pick_bcr_yosys_version(self.BCR, (0, 62)), "0.62.bcr.2")

    def test_below_minimum_raises(self):
        # Nothing in BCR is <= 0.56.
        with self.assertRaises(RuntimeError):
            bump.pick_bcr_yosys_version(self.BCR, (0, 56))


class TestUpdateBazelDepVersion(unittest.TestCase):
    """Unit tests for update_bazel_dep_version()."""

    def test_rewrites_matching_version(self):
        content = 'bazel_dep(name = "yosys", version = "0.62.bcr.2")\n'
        self.assertEqual(
            bump.update_bazel_dep_version(content, "yosys", "0.63"),
            'bazel_dep(name = "yosys", version = "0.63")\n',
        )

    def test_leaves_other_deps_alone(self):
        content = (
            'bazel_dep(name = "abc", version = "0.64-yosyshq.bcr.1")\n'
            'bazel_dep(name = "yosys", version = "0.62.bcr.2")\n'
        )
        result = bump.update_bazel_dep_version(content, "yosys", "0.63")
        self.assertIn('bazel_dep(name = "abc", version = "0.64-yosyshq.bcr.1")', result)
        self.assertIn('bazel_dep(name = "yosys", version = "0.63")', result)

    def test_noop_when_module_absent(self):
        content = 'bazel_dep(name = "abc", version = "0.64-yosyshq.bcr.1")\n'
        self.assertEqual(
            bump.update_bazel_dep_version(content, "yosys", "0.63"),
            content,
        )


class TestStrictModeFailures(unittest.TestCase):
    """Default mode: missing expected MODULE.bazel block -> BumpError."""

    def _run_on(self, content):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".MODULE.bazel", delete=False
        )
        tmp.write(content)
        tmp.close()
        try:
            bump.bump(
                tmp.name,
                fetch_commit_fn=mock_fetch_commit,
                fetch_integrity_fn=mock_fetch_integrity,
                fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
                fetch_compare_status_fn=mock_fetch_compare_status_ahead,
                fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
                fetch_bcr_versions_fn=mock_fetch_bcr_versions,
            )
            with open(tmp.name) as f:
                return f.read()
        finally:
            os.unlink(tmp.name)

    def test_missing_bazel_orfs_git_override_raises(self):
        # bazel_dep without matching git_override.
        content = (
            'module(name = "my-chip", version = "0.0.1")\n'
            'bazel_dep(name = "bazel-orfs")\n'
        )
        with self.assertRaises(bump.BumpError) as cm:
            self._run_on(content)
        self.assertIn("bazel-orfs", str(cm.exception))

    def test_missing_orfs_git_override_raises(self):
        # bazel-orfs handled, but orfs bazel_dep has no override block.
        content = (
            'module(name = "my-chip", version = "0.0.1")\n'
            'bazel_dep(name = "bazel-orfs")\n'
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            '    commit = "old",\n'
            '    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs.git",\n'
            ")\n"
            'bazel_dep(name = "orfs")\n'
        )
        with self.assertRaises(bump.BumpError) as cm:
            self._run_on(content)
        self.assertIn("orfs", str(cm.exception))

    def test_unexpected_yosys_version_shape_raises(self):
        # yosys bazel_dep present but version is variable-bound (not inline).
        content = (
            'module(name = "my-chip", version = "0.0.1")\n'
            'bazel_dep(name = "bazel-orfs")\n'
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            '    commit = "old",\n'
            '    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs.git",\n'
            ")\n"
            'bazel_dep(name = "orfs")\n'
            "git_override(\n"
            '    module_name = "orfs",\n'
            '    commit = "old",\n'
            '    remote = "https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts.git",\n'
            ")\n"
            'YOSYS_VERSION = "0.62.bcr.2"\n'
            'bazel_dep(name = "yosys", version = YOSYS_VERSION)\n'
        )
        with self.assertRaises(bump.BumpError) as cm:
            self._run_on(content)
        self.assertIn("yosys", str(cm.exception))


class TestIgnoreModeWarnsAndContinues(unittest.TestCase):
    """--ignore: missing blocks become warnings, recognizable parts still update."""

    def test_missing_orfs_block_warns_and_updates_bazel_orfs(self):
        content = (
            'module(name = "my-chip", version = "0.0.1")\n'
            'bazel_dep(name = "bazel-orfs")\n'
            "git_override(\n"
            '    module_name = "bazel-orfs",\n'
            '    commit = "old_bazel_orfs_commit",\n'
            '    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs.git",\n'
            ")\n"
            'bazel_dep(name = "orfs")\n'  # orfs lacks a git_override block
        )
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".MODULE.bazel", delete=False
        )
        tmp.write(content)
        tmp.close()
        try:
            # Captures warnings via stderr; primary check is no exception.
            bump.bump(
                tmp.name,
                fetch_commit_fn=mock_fetch_commit,
                fetch_integrity_fn=mock_fetch_integrity,
                fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
                fetch_compare_status_fn=mock_fetch_compare_status_ahead,
                fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
                fetch_bcr_versions_fn=mock_fetch_bcr_versions,
                ignore_errors=True,
            )
            with open(tmp.name) as f:
                result = f.read()
            # bazel-orfs was bumped; orfs left as-is.
            self.assertIn(BAZEL_ORFS_COMMIT, result)
            self.assertNotIn("old_bazel_orfs_commit", result)
        finally:
            os.unlink(tmp.name)


class TestCheckYosysAbcPair(unittest.TestCase):
    """Cover check_yosys_abc_pair — lockstep guard for downstream MODULE.bazel.

    YosysHQ/yosys's abc submodule pins a specific abc revision per yosys
    release; mixing an unrelated abc override has caused real synthesis
    quality regressions, so the bumper treats it as a hard error.
    """

    def test_neither_declared_is_ok(self):
        ok, msg = bump.check_yosys_abc_pair('module(name = "x")\n')
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_only_yosys_is_ok_with_skip_note(self):
        content = 'bazel_dep(name = "yosys", version = "0.63")\n'
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertTrue(ok)
        self.assertIn("only one of yosys/abc", msg)

    def test_only_abc_is_ok_with_skip_note(self):
        content = 'bazel_dep(name = "abc", version = "0.62-yosyshq")\n'
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertTrue(ok)
        self.assertIn("only one of yosys/abc", msg)

    def test_matched_pair_is_ok(self):
        content = (
            'bazel_dep(name = "yosys", version = "0.62")\n'
            'bazel_dep(name = "abc", version = "0.62-yosyshq")\n'
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_yosys_bcr_suffix_reduces_to_series(self):
        # 0.62.bcr.2 must collapse to series 0.62 -> abc 0.62-yosyshq.
        content = (
            'bazel_dep(name = "yosys", version = "0.62.bcr.2")\n'
            'bazel_dep(name = "abc", version = "0.62-yosyshq")\n'
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_mismatched_pair_fails_with_hint(self):
        content = (
            'bazel_dep(name = "yosys", version = "0.64")\n'
            'bazel_dep(name = "abc", version = "0.62-yosyshq")\n'
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertFalse(ok)
        self.assertIn("expects abc", msg)
        self.assertIn("'0.64-yosyshq.bcr.2'", msg)
        self.assertIn("'0.62-yosyshq'", msg)

    def test_yosys_version_without_bcr_abc_fails_as_unknown_series(self):
        # yosys 0.63 is on BCR but no matching abc is — the table omits 0.63
        # deliberately, so the check yields the 'no known pairing' error
        # rather than a misleading 'expected 0.63-yosyshq' suggestion.
        content = (
            'bazel_dep(name = "yosys", version = "0.63")\n'
            'bazel_dep(name = "abc", version = "0.64-yosyshq.bcr.1")\n'
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertFalse(ok)
        self.assertIn("no known abc pairing", msg)

    def test_unknown_yosys_series_fails(self):
        content = (
            'bazel_dep(name = "yosys", version = "9.99")\n'
            'bazel_dep(name = "abc", version = "9.99-yosyshq")\n'
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertFalse(ok)
        self.assertIn("no known abc pairing", msg)
        self.assertIn("YOSYS_ABC_PAIRS", msg)

    def test_abc_via_single_version_override_is_read(self):
        # downstream sometimes overrides via single_version_override.
        content = (
            'bazel_dep(name = "yosys", version = "0.62")\n'
            'bazel_dep(name = "abc")\n'
            "single_version_override(\n"
            '    module_name = "abc",\n'
            '    version = "0.62-yosyshq",\n'
            ")\n"
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_single_version_override_paren_in_patch_cmds_does_not_confuse_parser(self):
        # A patch_cmds triple-quoted string can contain ')' on its own line;
        # the parser must only treat ')' at column 0 as block end.
        content = (
            'bazel_dep(name = "yosys", version = "0.62")\n'
            'bazel_dep(name = "abc")\n'
            "single_version_override(\n"
            '    module_name = "abc",\n'
            '    version = "0.62-yosyshq",\n'
            '    patch_cmds = ["""sed -i \'s/foo(.*)/foo()/g\' file"""],\n'
            ")\n"
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_single_version_override_for_other_module_ignored(self):
        # An override on yosys (not abc) must not be picked up as abc's pin.
        content = (
            'bazel_dep(name = "yosys", version = "0.62")\n'
            "single_version_override(\n"
            '    module_name = "yosys",\n'
            '    version = "0.62",\n'
            ")\n"
        )
        ok, msg = bump.check_yosys_abc_pair(content)
        # yosys declared, abc not -> ok with skip note.
        self.assertTrue(ok)
        self.assertIn("only one of yosys/abc", msg)


class TestReadModuleHelpers(unittest.TestCase):
    """Cover the small parsing helpers feeding check_yosys_abc_pair."""

    def test_read_bazel_dep_version_basic(self):
        content = 'bazel_dep(name = "yosys", version = "0.63")\n'
        self.assertEqual(bump._read_bazel_dep_version(content, "yosys"), "0.63")

    def test_read_bazel_dep_version_missing(self):
        self.assertIsNone(bump._read_bazel_dep_version("", "yosys"))

    def test_read_bazel_dep_version_multiline(self):
        content = (
            "bazel_dep(\n" '    name = "yosys",\n' '    version = "0.62.bcr.2",\n' ")\n"
        )
        self.assertEqual(
            bump._read_bazel_dep_version(content, "yosys"),
            "0.62.bcr.2",
        )

    def test_read_bazel_dep_version_does_not_match_substring_module_name(self):
        # "yosys" must not match "yosys-slang".
        content = 'bazel_dep(name = "yosys-slang", version = "0.1")\n'
        self.assertIsNone(bump._read_bazel_dep_version(content, "yosys"))

    def test_read_single_version_override_basic(self):
        content = (
            "single_version_override(\n"
            '    module_name = "abc",\n'
            '    version = "0.65-yosyshq",\n'
            ")\n"
        )
        self.assertEqual(
            bump._read_single_version_override(content, "abc"),
            "0.65-yosyshq",
        )

    def test_read_single_version_override_missing(self):
        self.assertIsNone(bump._read_single_version_override("", "abc"))

    def test_yosys_major_minor_strips_bcr_suffix(self):
        self.assertEqual(bump._yosys_major_minor("0.62.bcr.2"), "0.62")

    def test_yosys_major_minor_plain(self):
        self.assertEqual(bump._yosys_major_minor("0.65"), "0.65")

    def test_yosys_major_minor_bad_input(self):
        self.assertIsNone(bump._yosys_major_minor("not-a-version"))


class TestOpenroadSubmoduleConversion(unittest.TestCase):
    """git_override(openroad, init_submodules=True) → archive_override + patch_cmds.

    The conversion eliminates the non-atomic submodule-fetch bug (where an
    interrupted fetch leaves empty ``src/sta/`` and Bazel reuses the broken
    state).  Replacement is archive_override over GitHub's auto-archive of
    the parent commit + curl-and-extract patch_cmds for OpenSTA / abc from
    their own GitHub auto-archives.
    """

    def setUp(self):
        # self.MODULE.bazel has git_override(openroad, init_submodules=True,
        # patches=[openroad-qt]) — the realistic shape this conversion targets.
        self.content = apply_bump("self.MODULE.bazel")
        span = bump.find_archive_override_block(self.content, "openroad")
        self.assertIsNotNone(span, "openroad must end up as archive_override")
        self.block = self.content[span[0] : span[1]]

    def test_no_git_override_left(self):
        self.assertIsNone(
            bump.find_git_override_block(self.content, "openroad"),
            "Legacy git_override(openroad,...) must be replaced, not duplicated",
        )

    def test_parent_url_uses_github_archive(self):
        self.assertIn(
            f"https://github.com/The-OpenROAD-Project/OpenROAD/archive/{OPENROAD_COMMIT}.tar.gz",
            self.block,
        )

    def test_parent_strip_prefix(self):
        self.assertIn(f'strip_prefix = "OpenROAD-{OPENROAD_COMMIT}"', self.block)

    def test_parent_integrity(self):
        self.assertIn(f'integrity = "{MOCK_INTEGRITY}"', self.block)

    def test_patch_cmds_vendors_opensta(self):
        sta_sha = OPENROAD_SUBMODULE_SHAS["src/sta"]
        self.assertIn(
            f"https://github.com/The-OpenROAD-Project/OpenSTA/archive/{sta_sha}.tar.gz",
            self.block,
        )
        # sha256sum -c verification line.
        self.assertIn(MOCK_SUB_SHA256_HEX, self.block)
        # Extracted into the empty src/sta/ directory left by the parent.
        self.assertIn("-C src/sta", self.block)

    def test_patch_cmds_vendors_abc(self):
        abc_sha = OPENROAD_SUBMODULE_SHAS["third-party/abc"]
        self.assertIn(
            f"https://github.com/The-OpenROAD-Project/abc/archive/{abc_sha}.tar.gz",
            self.block,
        )
        self.assertIn("-C third-party/abc", self.block)

    def test_curl_has_retry(self):
        # --retry guards against transient network blips during fetch
        # (mirrors the xcb-util-cursor pattern in //MODULE.bazel).
        self.assertIn("--retry 5", self.block)

    def test_existing_patches_preserved(self):
        self.assertIn(
            "//patches:openroad-10384-add-openroad-qt.patch",
            self.block,
        )
        self.assertIn("patch_strip = 1", self.block)

    def test_old_commit_gone(self):
        self.assertNotIn("old_openroad_commit", self.content)


class TestOpenroadConversionPreservesAbsentPatches(unittest.TestCase):
    """downstream.MODULE.bazel has no openroad patches — none must appear."""

    def setUp(self):
        self.content = apply_bump("downstream.MODULE.bazel")
        span = bump.find_archive_override_block(self.content, "openroad")
        self.assertIsNotNone(span)
        self.block = self.content[span[0] : span[1]]

    def test_no_patches_attribute(self):
        self.assertNotIn("patches = [", self.block)
        self.assertNotIn("patch_strip", self.block)


class TestOpenroadConversionIdempotent(unittest.TestCase):
    """Re-bumping a self.MODULE.bazel that's already archive_override is a no-op."""

    def test_double_bump_idempotent(self):
        src = os.path.join(FIXTURES_DIR, "self.MODULE.bazel")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".MODULE.bazel", delete=False
        )
        tmp.close()
        shutil.copy2(src, tmp.name)

        kwargs = dict(
            fetch_commit_fn=mock_fetch_commit,
            fetch_integrity_fn=mock_fetch_integrity,
            fetch_orfs_tool_sha_fn=mock_fetch_orfs_tool_sha,
            fetch_compare_status_fn=mock_fetch_compare_status_ahead,
            fetch_yosys_makefile_version_fn=mock_fetch_yosys_makefile_version,
            fetch_bcr_versions_fn=mock_fetch_bcr_versions,
            fetch_sha256_hex_fn=mock_fetch_sha256_hex,
            fetch_submodule_sha_fn=mock_fetch_submodule_sha,
        )
        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            first = f.read()
        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            second = f.read()
        os.unlink(tmp.name)
        self.assertEqual(first, second, "Second bump should be a no-op")


class TestUpdateOpenroadArchiveOverride(unittest.TestCase):
    """Direct unit test of the conversion function — no bump() orchestration."""

    def _stub_integrity(self, _url):
        return "sha256-PARENT="

    def _stub_sha256(self, _url):
        return "f" * 64

    def _stub_submodule_sha(self, _parent_repo, _parent_commit, path):
        return {
            "src/sta": "stasha",
            "third-party/abc": "abcsha",
            "third-party/slang-elab": "slangsha",
        }[path]

    def test_converts_git_override(self):
        content = (
            "git_override(\n"
            '    module_name = "openroad",\n'
            '    commit = "oldsha",\n'
            "    init_submodules = True,\n"
            '    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",\n'
            ")\n"
        )
        result = bump.update_openroad_archive_override(
            content,
            "newsha",
            fetch_integrity_fn=self._stub_integrity,
            fetch_sha256_hex_fn=self._stub_sha256,
            fetch_submodule_sha_fn=self._stub_submodule_sha,
        )
        self.assertIn("archive_override(", result)
        self.assertNotIn("git_override(", result)
        self.assertIn(
            "https://github.com/The-OpenROAD-Project/OpenROAD/archive/newsha.tar.gz",
            result,
        )
        self.assertIn("OpenSTA/archive/stasha.tar.gz", result)
        self.assertIn("abc/archive/abcsha.tar.gz", result)
        self.assertIn('integrity = "sha256-PARENT="', result)

    def test_no_op_when_openroad_absent(self):
        content = 'bazel_dep(name = "yosys", version = "0.63")\n'
        result = bump.update_openroad_archive_override(
            content,
            "newsha",
            fetch_integrity_fn=self._stub_integrity,
            fetch_sha256_hex_fn=self._stub_sha256,
            fetch_submodule_sha_fn=self._stub_submodule_sha,
        )
        self.assertEqual(result, content)

    def test_updates_existing_archive_override(self):
        # Pre-existing archive_override — must be regenerated against new commit.
        content = (
            "archive_override(\n"
            '    module_name = "openroad",\n'
            '    integrity = "sha256-OLD=",\n'
            "    patch_cmds = [\n"
            '        "curl ... oldsta ...",\n'
            "    ],\n"
            '    strip_prefix = "OpenROAD-oldsha",\n'
            '    urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/oldsha.tar.gz"],\n'
            ")\n"
        )
        result = bump.update_openroad_archive_override(
            content,
            "newsha",
            fetch_integrity_fn=self._stub_integrity,
            fetch_sha256_hex_fn=self._stub_sha256,
            fetch_submodule_sha_fn=self._stub_submodule_sha,
        )
        self.assertIn("newsha.tar.gz", result)
        self.assertNotIn("oldsha", result)
        self.assertIn("stasha", result)
        self.assertIn("abcsha", result)

    def test_preserves_patches_during_conversion(self):
        content = (
            "git_override(\n"
            '    module_name = "openroad",\n'
            '    commit = "old",\n'
            "    init_submodules = True,\n"
            "    patch_strip = 1,\n"
            "    patches = [\n"
            '        "//patches:openroad-foo.patch",\n'
            "    ],\n"
            '    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",\n'
            ")\n"
        )
        result = bump.update_openroad_archive_override(
            content,
            "new",
            fetch_integrity_fn=self._stub_integrity,
            fetch_sha256_hex_fn=self._stub_sha256,
            fetch_submodule_sha_fn=self._stub_submodule_sha,
        )
        self.assertIn("//patches:openroad-foo.patch", result)
        self.assertIn("patch_strip = 1", result)


if __name__ == "__main__":
    unittest.main()
