import unittest
import bump_impl

class TestUpdateOpenroadArchiveOverride(unittest.TestCase):
    def test_preserves_custom_comments(self):
        content = """archive_override(
    module_name = "openroad",
    integrity = "sha256-foo",
    patch_cmds = [],
    patches = [
        # This is a custom comment for foo
        "//orfs-patches:foo.patch",
        # This is a custom comment for bar
        # another line of comment
        "//orfs-patches:bar.patch",
    ],
    strip_prefix = "OpenROAD-12345",
    urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/12345.tar.gz"],
)
"""
        # Mocking the fetch functions and workspace_dir = None (no file check)
        def mock_fetch_integrity(url):
            return "sha256-bar"
        
        def mock_fetch_sha256_hex(url):
            return "bar_hex"

        def mock_fetch_submodule(repo, commit, path):
            return ("new_sub_sha", "new_sub_sha256_hex")

        new_content = bump_impl.update_openroad_archive_override(
            content=content,
            openroad_commit="67890",
            fetch_integrity_fn=mock_fetch_integrity,
            fetch_sha256_hex_fn=mock_fetch_sha256_hex,
            fetch_submodule_sha_fn=mock_fetch_submodule,
            workspace_dir=None,
        )

        self.assertIn("archive_override", new_content)
        self.assertIn("# This is a custom comment for foo", new_content)
        self.assertIn("# This is a custom comment for bar", new_content)
        self.assertIn("# another line of comment", new_content)

        # Check association: foo comment should appear before foo.patch
        foo_comment_idx = new_content.find("# This is a custom comment for foo")
        foo_patch_idx = new_content.find('"//orfs-patches:foo.patch"')
        self.assertLess(foo_comment_idx, foo_patch_idx)

        # Check association: bar comments should appear before bar.patch
        bar_comment1_idx = new_content.find("# This is a custom comment for bar")
        bar_comment2_idx = new_content.find("# another line of comment")
        bar_patch_idx = new_content.find('"//orfs-patches:bar.patch"')
        self.assertLess(bar_comment1_idx, bar_patch_idx)
        self.assertLess(bar_comment2_idx, bar_patch_idx)

    def test_preserves_trailing_comments(self):
        content = """archive_override(
    module_name = "openroad",
    integrity = "sha256-foo",
    patch_cmds = [],
    patches = [
        "//orfs-patches:foo.patch",
    ],
    # This is a trailing comment
    # Another trailing comment
    strip_prefix = "OpenROAD-12345",
    urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/12345.tar.gz"],
)
"""
        def mock_fetch_integrity(url):
            return "sha256-bar"

        new_content = bump_impl.update_openroad_archive_override(
            content=content,
            openroad_commit="67890",
            fetch_integrity_fn=mock_fetch_integrity,
            fetch_sha256_hex_fn=lambda u: "bar_hex",
            fetch_submodule_sha_fn=lambda r, c, p: ("new_sub_sha", "new_sub_sha256_hex"),
            workspace_dir=None,
        )

        self.assertIn("# This is a trailing comment", new_content)
        self.assertIn("# Another trailing comment", new_content)
        trailing_idx = new_content.find("# This is a trailing comment")
        strip_idx = new_content.find('strip_prefix = "OpenROAD-67890"')
        self.assertLess(trailing_idx, strip_idx)

if __name__ == "__main__":
    unittest.main()
