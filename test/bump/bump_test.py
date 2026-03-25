#!/usr/bin/env python3
"""Unit tests for bump.py — ported from bump_test.sh with additions."""

import os
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


def apply_bump(fixture_name, mock_modules=None):
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
    )

    with open(tmp.name) as f:
        content = f.read()
    os.unlink(tmp.name)
    return content


class TestBazelOrfsProject(unittest.TestCase):
    """Test 1: bazel-orfs project (self)."""

    def setUp(self):
        self.content = apply_bump("self.MODULE.bazel")

    def test_docker_image_tag_updated(self):
        self.assertIn(LATEST_TAG, self.content)

    def test_docker_sha256_updated(self):
        self.assertIn(DIGEST, self.content)

    def test_openroad_commit_updated(self):
        self.assertIn(OPENROAD_COMMIT, self.content)

    def test_bazel_orfs_commit_not_updated(self):
        self.assertNotIn(
            BAZEL_ORFS_COMMIT,
            self.content,
            "bazel-orfs should not update its own commit",
        )

    def test_no_boilerplate_injected(self):
        self.assertNotIn(bump.BOILERPLATE_MARKER, self.content)


class TestOpenroadProject(unittest.TestCase):
    """Test 2: OpenROAD project."""

    def setUp(self):
        self.content = apply_bump("openroad.MODULE.bazel")

    def test_docker_image_tag_updated(self):
        self.assertIn(LATEST_TAG, self.content)

    def test_docker_sha256_updated(self):
        self.assertIn(DIGEST, self.content)

    def test_bazel_orfs_commit_updated(self):
        self.assertIn(BAZEL_ORFS_COMMIT, self.content)

    def test_openroad_commit_not_updated(self):
        self.assertNotIn(
            OPENROAD_COMMIT, self.content, "OpenROAD should not update its own commit"
        )

    def test_no_boilerplate_injected(self):
        self.assertNotIn(bump.BOILERPLATE_MARKER, self.content)

    def test_openroad_label_preserved(self):
        self.assertIn('openroad = "//:openroad"', self.content)


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
                )
            finally:
                os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
