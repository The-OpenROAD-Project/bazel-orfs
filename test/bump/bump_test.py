#!/usr/bin/env python3
"""Unit tests for bump.py — ported from bump_test.sh with additions."""

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
LATEST_TAG = "26Q1-999-gtest12345"
DIGEST = "deadbeef1234567890abcdef"
BAZEL_ORFS_COMMIT = "new_bazel_orfs_aaa111"
OPENROAD_COMMIT = "new_openroad_bbb222"
ORFS_COMMIT = "new_orfs_ccc333"
YOSYS_TAG = "v0.99"
YOSYS_TAG_COMMIT = "new_yosys_ddd444"

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def mock_fetch_tag(_repo):
    return LATEST_TAG


def mock_fetch_commit(repo, branch):
    if "bazel-orfs" in repo:
        return BAZEL_ORFS_COMMIT
    if "OpenROAD-flow-scripts" in repo:
        return ORFS_COMMIT
    return OPENROAD_COMMIT


def mock_resolve_digest(_image, _tag):
    return DIGEST


def mock_fetch_release(_repo):
    return YOSYS_TAG


def mock_fetch_tag_commit(_repo, _tag):
    return YOSYS_TAG_COMMIT


def apply_bump(fixture_name, mock_modules=None, workspace_dir=None):
    """Copy a fixture, run bump on it, return the result content."""
    src = os.path.join(FIXTURES_DIR, fixture_name)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".MODULE.bazel", delete=False)
    tmp.close()
    shutil.copy2(src, tmp.name)

    bump.bump(
        tmp.name,
        mock_modules=mock_modules,
        fetch_tag_fn=mock_fetch_tag,
        fetch_commit_fn=mock_fetch_commit,
        resolve_digest_fn=mock_resolve_digest,
        fetch_release_fn=mock_fetch_release,
        fetch_tag_commit_fn=mock_fetch_tag_commit,
        workspace_dir=workspace_dir,
    )

    with open(tmp.name) as f:
        content = f.read()
    os.unlink(tmp.name)
    return content


class TestBazelOrfsProject(unittest.TestCase):
    """Test 1: bazel-orfs project (self)."""

    def setUp(self):
        self.content = apply_bump("self.MODULE.bazel")

    def test_no_docker_image_tag(self):
        self.assertNotIn(
            LATEST_TAG,
            self.content,
            "bazel-orfs no longer uses a Docker image",
        )

    def test_no_docker_sha256(self):
        self.assertNotIn("sha256", self.content)

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

    def test_no_boilerplate_injected(self):
        self.assertNotIn(bump.BOILERPLATE_MARKER, self.content)


class TestOpenroadProject(unittest.TestCase):
    """Test 2: OpenROAD project (uses variable-reference commit pattern)."""

    def setUp(self):
        self.content = apply_bump("openroad.MODULE.bazel")

    def test_docker_image_tag_updated(self):
        self.assertIn(LATEST_TAG, self.content)

    def test_docker_sha256_updated(self):
        self.assertIn(DIGEST, self.content)

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

    def test_no_boilerplate_injected(self):
        self.assertNotIn(bump.BOILERPLATE_MARKER, self.content)

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
    """Test 3: downstream project (no prior boilerplate)."""

    def setUp(self):
        self.content = apply_bump("downstream.MODULE.bazel")

    def test_docker_image_tag_updated(self):
        self.assertIn(LATEST_TAG, self.content)

    def test_docker_sha256_updated(self):
        self.assertIn(DIGEST, self.content)

    def test_bazel_orfs_commit_updated(self):
        self.assertIn(BAZEL_ORFS_COMMIT, self.content)

    def test_boilerplate_injected(self):
        self.assertIn(bump.BOILERPLATE_MARKER, self.content)

    def test_boilerplate_has_openroad_commit(self):
        self.assertIn(f'commit = "{OPENROAD_COMMIT}"', self.content)


class TestDownstreamWithBoilerplate(unittest.TestCase):
    """Test 4: downstream project (already has boilerplate)."""

    def setUp(self):
        self.content = apply_bump("downstream-with-boilerplate.MODULE.bazel")

    def test_docker_image_tag_updated(self):
        self.assertIn(LATEST_TAG, self.content)

    def test_docker_sha256_updated(self):
        self.assertIn(DIGEST, self.content)

    def test_bazel_orfs_commit_updated(self):
        self.assertIn(BAZEL_ORFS_COMMIT, self.content)

    def test_old_openroad_commit_replaced(self):
        self.assertNotIn("old_openroad_commit", self.content)

    def test_new_openroad_commit_present(self):
        self.assertIn(f'commit = "{OPENROAD_COMMIT}"', self.content)

    def test_boilerplate_not_duplicated(self):
        count = self.content.count(bump.BOILERPLATE_MARKER)
        self.assertEqual(count, 1, f"Boilerplate appears {count} times, expected 1")


class TestDownstreamWithSubmodules(unittest.TestCase):
    """Test: downstream with bazel-orfs-verilog and bazel-orfs-sby submodules."""

    def setUp(self):
        self.content = apply_bump("downstream-with-submodules.MODULE.bazel")

    def test_bazel_orfs_commit_updated(self):
        self.assertNotIn("old_bazel_orfs_commit", self.content)

    def test_verilog_submodule_commit_updated(self):
        self.assertNotIn("old_verilog_commit", self.content)

    def test_sby_submodule_commit_updated(self):
        self.assertNotIn("old_sby_commit", self.content)

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
        self.assertEqual(commits["bazel-orfs-sby"], BAZEL_ORFS_COMMIT)

    def test_strip_prefix_preserved(self):
        self.assertIn('strip_prefix = "verilog"', self.content)
        self.assertIn('strip_prefix = "sby"', self.content)


class TestDownstreamSubmodulesInjected(unittest.TestCase):
    """Bump should inject submodule overrides for downstream projects."""

    def setUp(self):
        self.content = apply_bump("downstream.MODULE.bazel")

    def test_verilog_submodule_injected(self):
        self.assertIn("bazel-orfs-verilog", self.content)

    def test_sby_submodule_injected(self):
        self.assertIn("bazel-orfs-sby", self.content)


class TestFindBazelOrfsSubmodules(unittest.TestCase):
    def test_finds_present_submodules(self):
        content = (
            'git_override(\n    module_name = "bazel-orfs-sby",\n'
            '    commit = "abc",\n)\n'
        )
        self.assertEqual(bump.find_bazel_orfs_submodules(content), ["bazel-orfs-sby"])

    def test_empty_when_none_present(self):
        content = (
            'git_override(\n    module_name = "bazel-orfs",\n    commit = "x",\n)\n'
        )
        self.assertEqual(bump.find_bazel_orfs_submodules(content), [])

    def test_finds_both(self):
        content = (
            'git_override(\n    module_name = "bazel-orfs-verilog",\n    commit = "a",\n)\n'
            'git_override(\n    module_name = "bazel-orfs-sby",\n    commit = "b",\n)\n'
        )
        self.assertEqual(
            bump.find_bazel_orfs_submodules(content),
            ["bazel-orfs-verilog", "bazel-orfs-sby"],
        )


class TestDownstreamDoubleBump(unittest.TestCase):
    """Test 5: downstream project — bump twice, still idempotent."""

    def test_boilerplate_appears_once(self):
        src = os.path.join(FIXTURES_DIR, "downstream.MODULE.bazel")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".MODULE.bazel", delete=False
        )
        tmp.close()
        shutil.copy2(src, tmp.name)

        kwargs = dict(
            fetch_tag_fn=mock_fetch_tag,
            fetch_commit_fn=mock_fetch_commit,
            resolve_digest_fn=mock_resolve_digest,
            fetch_release_fn=mock_fetch_release,
            fetch_tag_commit_fn=mock_fetch_tag_commit,
        )
        bump.bump(tmp.name, **kwargs)
        bump.bump(tmp.name, **kwargs)

        with open(tmp.name) as f:
            content = f.read()
        os.unlink(tmp.name)

        count = content.count(bump.BOILERPLATE_MARKER)
        self.assertEqual(
            count,
            1,
            f"After double bump, boilerplate appears " f"{count} times (expected 1)",
        )


class TestBazelOrfsYosysUpdate(unittest.TestCase):
    """bazel-orfs project updates yosys commit in extension.bzl."""

    def test_yosys_commit_updated_in_extension(self):
        tmpdir = tempfile.mkdtemp()
        try:
            main_file = os.path.join(tmpdir, "MODULE.bazel")
            shutil.copy2(
                os.path.join(FIXTURES_DIR, "self.MODULE.bazel"),
                main_file,
            )

            ext_file = os.path.join(tmpdir, "extension.bzl")
            with open(ext_file, "w") as f:
                f.write(
                    "yosys_build(\n"
                    '    name = "yosys",\n'
                    '    yosys_commit = "old_yosys_commit",\n'
                    ")\n"
                )

            bump.bump(
                main_file,
                fetch_tag_fn=mock_fetch_tag,
                fetch_commit_fn=mock_fetch_commit,
                resolve_digest_fn=mock_resolve_digest,
                fetch_release_fn=mock_fetch_release,
                fetch_tag_commit_fn=mock_fetch_tag_commit,
                workspace_dir=tmpdir,
            )

            with open(ext_file) as f:
                ext_content = f.read()

            self.assertIn(YOSYS_TAG_COMMIT, ext_content)
            self.assertNotIn("old_yosys_commit", ext_content)
        finally:
            shutil.rmtree(tmpdir)


class TestBazelOrfsDockerImageUpdate(unittest.TestCase):
    """bazel-orfs project updates Docker image constants in extension.bzl."""

    def test_docker_image_constants_updated(self):
        tmpdir = tempfile.mkdtemp()
        try:
            main_file = os.path.join(tmpdir, "MODULE.bazel")
            shutil.copy2(
                os.path.join(FIXTURES_DIR, "self.MODULE.bazel"),
                main_file,
            )

            ext_file = os.path.join(tmpdir, "extension.bzl")
            with open(ext_file, "w") as f:
                f.write(
                    'LATEST_ORFS_IMAGE = "docker.io/openroad/orfs:old-tag"\n'
                    'LATEST_ORFS_SHA256 = "olddigest"\n'
                )

            bump.bump(
                main_file,
                fetch_tag_fn=mock_fetch_tag,
                fetch_commit_fn=mock_fetch_commit,
                resolve_digest_fn=mock_resolve_digest,
                fetch_release_fn=mock_fetch_release,
                fetch_tag_commit_fn=mock_fetch_tag_commit,
                workspace_dir=tmpdir,
            )

            with open(ext_file) as f:
                ext_content = f.read()

            self.assertIn(LATEST_TAG, ext_content)
            self.assertIn(DIGEST, ext_content)
            self.assertNotIn("old-tag", ext_content)
            self.assertNotIn("olddigest", ext_content)
        finally:
            shutil.rmtree(tmpdir)


class TestMockModuleUpdates(unittest.TestCase):
    """Test 6: mock/*/MODULE.bazel files also get updated."""

    def test_mock_modules_updated(self):
        tmpdir = tempfile.mkdtemp()
        try:
            # Copy main fixture
            main_file = os.path.join(tmpdir, "MODULE.bazel")
            shutil.copy2(
                os.path.join(FIXTURES_DIR, "self.MODULE.bazel"),
                main_file,
            )

            # Create a mock module
            mock_file = os.path.join(tmpdir, "mock.MODULE.bazel")
            shutil.copy2(
                os.path.join(FIXTURES_DIR, "downstream.MODULE.bazel"),
                mock_file,
            )

            bump.bump(
                main_file,
                mock_modules=[mock_file],
                fetch_tag_fn=mock_fetch_tag,
                fetch_commit_fn=mock_fetch_commit,
                resolve_digest_fn=mock_resolve_digest,
                fetch_release_fn=mock_fetch_release,
                fetch_tag_commit_fn=mock_fetch_tag_commit,
            )

            with open(mock_file) as f:
                mock_content = f.read()

            self.assertIn(LATEST_TAG, mock_content)
            self.assertIn(DIGEST, mock_content)
        finally:
            shutil.rmtree(tmpdir)


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


class TestUpdateOrfsImage(unittest.TestCase):
    def test_updates_tag_and_digest(self):
        content = (
            "orfs.default(\n"
            '    image = "docker.io/openroad/orfs:OLD-TAG",\n'
            '    sha256 = "old_sha256",\n'
            ")"
        )
        result = bump.update_orfs_image(content, "NEW-TAG", "new_digest")
        self.assertIn("NEW-TAG", result)
        self.assertIn("new_digest", result)
        self.assertNotIn("OLD-TAG", result)
        self.assertNotIn("old_sha256", result)

    def test_preserves_other_fields(self):
        content = (
            "orfs.default(\n"
            '    image = "docker.io/openroad/orfs:OLD",\n'
            '    openroad = "//:openroad",\n'
            '    sha256 = "old",\n'
            ")"
        )
        result = bump.update_orfs_image(content, "NEW", "new")
        self.assertIn('openroad = "//:openroad"', result)

    def test_no_orfs_default_is_noop(self):
        content = 'module(name = "foo")\n'
        result = bump.update_orfs_image(content, "TAG", "DIGEST")
        self.assertEqual(result, content)

    def test_preserves_surrounding_content(self):
        content = (
            "# header\n"
            "orfs.default(\n"
            '    image = "docker.io/openroad/orfs:OLD",\n'
            '    sha256 = "old",\n'
            ")\n"
            "# footer\n"
        )
        result = bump.update_orfs_image(content, "NEW", "new")
        self.assertTrue(result.startswith("# header\n"))
        self.assertTrue(result.endswith("# footer\n"))


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


class TestInjectBoilerplate(unittest.TestCase):
    def test_injects_after_use_repo(self):
        content = 'use_repo(orfs, "docker_orfs")\n' "\n" "# other stuff\n"
        result = bump.inject_openroad_boilerplate(content, "abc123")
        self.assertIn(bump.BOILERPLATE_MARKER, result)
        self.assertIn('commit = "abc123"', result)

    def test_does_not_duplicate(self):
        content = 'use_repo(orfs, "docker_orfs")\n' f"\n# {bump.BOILERPLATE_MARKER}\n"
        result = bump.inject_openroad_boilerplate(content, "abc123")
        count = result.count(bump.BOILERPLATE_MARKER)
        self.assertEqual(count, 1)

    def test_no_use_repo_is_noop(self):
        content = 'module(name = "test")\n'
        result = bump.inject_openroad_boilerplate(content, "abc123")
        self.assertNotIn(bump.BOILERPLATE_MARKER, result)
        self.assertEqual(result, content)

    def test_boilerplate_placed_after_last_use_repo(self):
        content = (
            'use_repo(orfs, "docker_orfs")\n' 'use_repo(orfs, "other")\n' "# end\n"
        )
        result = bump.inject_openroad_boilerplate(content, "abc123")
        lines = result.split("\n")
        marker_idx = next(
            i for i, l in enumerate(lines) if bump.BOILERPLATE_MARKER in l
        )
        use_repo_indices = [i for i, l in enumerate(lines) if "use_repo(orfs" in l]
        self.assertGreater(marker_idx, max(use_repo_indices))


class TestBazelOrfsSkipsSelfCommit(unittest.TestCase):
    """bazel-orfs project must not update its own git_override commit."""

    def setUp(self):
        self.content = apply_bump("self.MODULE.bazel")

    def test_orfs_commit_updated(self):
        self.assertIn(
            ORFS_COMMIT, self.content, "ORFS commit should be updated for bazel-orfs"
        )

    def test_no_image_tag(self):
        self.assertNotIn(
            LATEST_TAG,
            self.content,
            "bazel-orfs no longer uses a Docker image",
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
            fetch_tag_fn=mock_fetch_tag,
            fetch_commit_fn=mock_fetch_commit,
            resolve_digest_fn=mock_resolve_digest,
            fetch_release_fn=mock_fetch_release,
            fetch_tag_commit_fn=mock_fetch_tag_commit,
        )
        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            first = f.read()

        bump.bump(tmp.name, **kwargs)
        with open(tmp.name) as f:
            second = f.read()

        os.unlink(tmp.name)
        self.assertEqual(first, second, "Second bump should produce identical output")


class TestMockModuleSkipsNonOrfs(unittest.TestCase):
    """Mock modules without orfs.default() should be left untouched."""

    def test_mock_without_orfs_default_unchanged(self):
        tmpdir = tempfile.mkdtemp()
        try:
            main_file = os.path.join(tmpdir, "MODULE.bazel")
            shutil.copy2(
                os.path.join(FIXTURES_DIR, "self.MODULE.bazel"),
                main_file,
            )

            mock_file = os.path.join(tmpdir, "mock.MODULE.bazel")
            with open(mock_file, "w") as f:
                f.write('module(name = "mock")\n')

            original = open(mock_file).read()

            bump.bump(
                main_file,
                mock_modules=[mock_file],
                fetch_tag_fn=mock_fetch_tag,
                fetch_commit_fn=mock_fetch_commit,
                resolve_digest_fn=mock_resolve_digest,
                fetch_release_fn=mock_fetch_release,
                fetch_tag_commit_fn=mock_fetch_tag_commit,
            )

            with open(mock_file) as f:
                self.assertEqual(f.read(), original)
        finally:
            shutil.rmtree(tmpdir)


class TestMockModuleMissingFile(unittest.TestCase):
    """Mock modules that don't exist should be silently skipped."""

    def test_missing_mock_file_no_error(self):
        src = os.path.join(FIXTURES_DIR, "self.MODULE.bazel")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".MODULE.bazel", delete=False
        )
        tmp.close()
        shutil.copy2(src, tmp.name)
        try:
            bump.bump(
                tmp.name,
                mock_modules=["/nonexistent/MODULE.bazel"],
                fetch_tag_fn=mock_fetch_tag,
                fetch_commit_fn=mock_fetch_commit,
                resolve_digest_fn=mock_resolve_digest,
                fetch_release_fn=mock_fetch_release,
                fetch_tag_commit_fn=mock_fetch_tag_commit,
            )
        finally:
            os.unlink(tmp.name)


class TestNetworkErrorHandling(unittest.TestCase):
    """Test 7: verify clear error messages on failures."""

    def test_tag_fetch_failure(self):
        def bad_fetch(_repo):
            raise RuntimeError("No tags found")

        with self.assertRaises(RuntimeError):
            src = os.path.join(FIXTURES_DIR, "self.MODULE.bazel")
            tmp = tempfile.NamedTemporaryFile(suffix=".MODULE.bazel", delete=False)
            tmp.close()
            shutil.copy2(src, tmp.name)
            try:
                bump.bump(
                    tmp.name,
                    fetch_tag_fn=bad_fetch,
                    fetch_commit_fn=mock_fetch_commit,
                    resolve_digest_fn=mock_resolve_digest,
                    fetch_release_fn=mock_fetch_release,
                    fetch_tag_commit_fn=mock_fetch_tag_commit,
                )
            finally:
                os.unlink(tmp.name)

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
                    fetch_tag_fn=mock_fetch_tag,
                    fetch_commit_fn=bad_commit,
                    resolve_digest_fn=mock_resolve_digest,
                    fetch_release_fn=mock_fetch_release,
                    fetch_tag_commit_fn=mock_fetch_tag_commit,
                )
            finally:
                os.unlink(tmp.name)

    def test_digest_resolve_failure(self):
        def bad_digest(_image, _tag):
            raise RuntimeError("Registry error")

        with self.assertRaises(RuntimeError):
            src = os.path.join(FIXTURES_DIR, "self.MODULE.bazel")
            tmp = tempfile.NamedTemporaryFile(suffix=".MODULE.bazel", delete=False)
            tmp.close()
            shutil.copy2(src, tmp.name)
            try:
                bump.bump(
                    tmp.name,
                    fetch_tag_fn=mock_fetch_tag,
                    fetch_commit_fn=mock_fetch_commit,
                    resolve_digest_fn=bad_digest,
                    fetch_release_fn=mock_fetch_release,
                    fetch_tag_commit_fn=mock_fetch_tag_commit,
                )
            finally:
                os.unlink(tmp.name)


class TestMigrateLoadPaths(unittest.TestCase):
    """Test load() path migration for moved .bzl files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, relpath, content):
        fpath = os.path.join(self.tmpdir, relpath)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w") as f:
            f.write(content)
        return fpath

    def _read(self, relpath):
        with open(os.path.join(self.tmpdir, relpath)) as f:
            return f.read()

    def test_migrates_sby_load_in_build_file(self):
        self._write(
            "hardware/BUILD.bazel",
            'load("@bazel-orfs//:sby.bzl", "sby_test")\n',
        )
        changes = bump.migrate_load_paths(self.tmpdir)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][1], "@bazel-orfs//:sby.bzl")
        self.assertEqual(changes[0][2], "@bazel-orfs//:sby/sby.bzl")
        self.assertEqual(
            self._read("hardware/BUILD.bazel"),
            'load("@bazel-orfs//:sby/sby.bzl", "sby_test")\n',
        )

    def test_migrates_sby_load_in_bzl_file(self):
        self._write(
            "defs.bzl",
            'load("@bazel-orfs//:sby.bzl", "sby_test")\n',
        )
        changes = bump.migrate_load_paths(self.tmpdir)
        self.assertEqual(len(changes), 1)

    def test_skips_already_migrated(self):
        self._write(
            "BUILD.bazel",
            'load("@bazel-orfs//:sby/sby.bzl", "sby_test")\n',
        )
        changes = bump.migrate_load_paths(self.tmpdir)
        self.assertEqual(len(changes), 0)

    def test_skips_unrelated_files(self):
        self._write("README.md", "@bazel-orfs//:sby.bzl\n")
        self._write("src/main.py", 'print("@bazel-orfs//:sby.bzl")\n')
        changes = bump.migrate_load_paths(self.tmpdir)
        self.assertEqual(len(changes), 0)

    def test_skips_bazel_output_dirs(self):
        self._write(
            "bazel-bin/BUILD.bazel",
            'load("@bazel-orfs//:sby.bzl", "sby_test")\n',
        )
        changes = bump.migrate_load_paths(self.tmpdir)
        self.assertEqual(len(changes), 0)

    def test_skips_hidden_dirs(self):
        self._write(
            ".git/BUILD.bazel",
            'load("@bazel-orfs//:sby.bzl", "sby_test")\n',
        )
        changes = bump.migrate_load_paths(self.tmpdir)
        self.assertEqual(len(changes), 0)

    def test_migrates_multiple_files(self):
        self._write(
            "a/BUILD.bazel",
            'load("@bazel-orfs//:sby.bzl", "sby_test")\n',
        )
        self._write(
            "b/BUILD",
            'load("@bazel-orfs//:sby.bzl", "sby_test")\n',
        )
        changes = bump.migrate_load_paths(self.tmpdir)
        self.assertEqual(len(changes), 2)

    def test_preserves_other_loads(self):
        content = (
            'load("@bazel-orfs//:sby.bzl", "sby_test")\n'
            'load("@bazel-orfs//:openroad.bzl", "orfs_flow")\n'
        )
        self._write("BUILD.bazel", content)
        bump.migrate_load_paths(self.tmpdir)
        result = self._read("BUILD.bazel")
        self.assertIn("@bazel-orfs//:sby/sby.bzl", result)
        self.assertIn("@bazel-orfs//:openroad.bzl", result)


class TestBumpWithMigration(unittest.TestCase):
    """Integration test: bump() migrates load paths in workspace."""

    def test_bump_migrates_sby_load(self):
        tmpdir = tempfile.mkdtemp()
        try:
            # Set up workspace with MODULE.bazel and a BUILD file with old load
            src = os.path.join(FIXTURES_DIR, "downstream.MODULE.bazel")
            module_file = os.path.join(tmpdir, "MODULE.bazel")
            shutil.copy2(src, module_file)

            build_file = os.path.join(tmpdir, "hardware", "BUILD.bazel")
            os.makedirs(os.path.dirname(build_file))
            with open(build_file, "w") as f:
                f.write('load("@bazel-orfs//:sby.bzl", "sby_test")\n')

            bump.bump(
                module_file,
                fetch_tag_fn=mock_fetch_tag,
                fetch_commit_fn=mock_fetch_commit,
                resolve_digest_fn=mock_resolve_digest,
                fetch_release_fn=mock_fetch_release,
                fetch_tag_commit_fn=mock_fetch_tag_commit,
                workspace_dir=tmpdir,
            )

            with open(build_file) as f:
                result = f.read()
            self.assertIn("@bazel-orfs//:sby/sby.bzl", result)
            self.assertNotIn('@bazel-orfs//:sby.bzl"', result)
        finally:
            shutil.rmtree(tmpdir)

    def test_bazel_orfs_project_skips_migration(self):
        """bazel-orfs itself should not migrate its own load paths."""
        tmpdir = tempfile.mkdtemp()
        try:
            src = os.path.join(FIXTURES_DIR, "self.MODULE.bazel")
            module_file = os.path.join(tmpdir, "MODULE.bazel")
            shutil.copy2(src, module_file)

            build_file = os.path.join(tmpdir, "BUILD.bazel")
            with open(build_file, "w") as f:
                f.write('load("//:sby.bzl", "sby_test")\n')

            bump.bump(
                module_file,
                fetch_tag_fn=mock_fetch_tag,
                fetch_commit_fn=mock_fetch_commit,
                resolve_digest_fn=mock_resolve_digest,
                fetch_release_fn=mock_fetch_release,
                fetch_tag_commit_fn=mock_fetch_tag_commit,
                workspace_dir=tmpdir,
            )

            with open(build_file) as f:
                result = f.read()
            # bazel-orfs uses //:sby.bzl (no @bazel-orfs prefix), should be untouched
            self.assertEqual(result, 'load("//:sby.bzl", "sby_test")\n')
        finally:
            shutil.rmtree(tmpdir)


if __name__ == "__main__":
    unittest.main()
