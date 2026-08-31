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
            fetch_submodule_sha_fn=lambda r, c, p: (
                "new_sub_sha",
                "new_sub_sha256_hex",
            ),
            workspace_dir=None,
        )

        self.assertIn("# This is a trailing comment", new_content)
        self.assertIn("# Another trailing comment", new_content)
        trailing_idx = new_content.find("# This is a trailing comment")
        strip_idx = new_content.find('strip_prefix = "OpenROAD-67890"')
        self.assertLess(trailing_idx, strip_idx)


OLD_SHA = "a" * 40
NEW_SHA = "b" * 40
OLD_HEX = "c" * 64
NEW_HEX = "d" * 64
MIRROR = "https://mirror.example.com/openroad"


def _submodule_cmd(path, fetch=None, sha=OLD_SHA, sha256=OLD_HEX):
    """A generated submodule patch_cmd, optionally with a mirrored fetch."""
    stagefile = f".openroad-submodule-{path.replace('/', '-')}-{sha}.tar.gz"
    if fetch is None:
        fetch = (
            "curl -sSfL --retry 5 --retry-all-errors --retry-delay 5 "
            f"-o {stagefile} https://github.com/The-OpenROAD-Project/x/archive/{sha}.tar.gz"
        )
    return (
        f"{fetch} && echo '{sha256}  {stagefile}' | sha256sum -c - && "
        f"tar xzf {stagefile} --strip-components=1 -C {path} && rm {stagefile}"
    )


def _block(patch_cmds=(), urls=None):
    if urls is None:
        urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/12345.tar.gz"]
    cmd_lines = "".join(f"        {cmd!r},\n" for cmd in patch_cmds)
    url_lines = "".join(f'        "{u}",\n' for u in urls)
    return f"""archive_override(
    module_name = "openroad",
    integrity = "sha256-foo",
    patch_cmds = [
{cmd_lines}    ],
    strip_prefix = "OpenROAD-12345",
    urls = [
{url_lines}    ],
)
"""


def _regenerate(content, commit="67890"):
    return bump_impl.update_openroad_archive_override(
        content=content,
        openroad_commit=commit,
        fetch_integrity_fn=lambda u: "sha256-bar",
        fetch_sha256_hex_fn=lambda u: NEW_HEX,
        fetch_submodule_sha_fn=lambda r, c, p: NEW_SHA,
        workspace_dir=None,
    )


class TestMirrorPreservation(unittest.TestCase):
    """A consumer's mirrors are configuration, not hand-edits to undo.

    GitHub's codeload cache can serve HTTP 400 for the tar.gz-by-sha key of an
    individual commit, so a consumer may have to fetch an archive from a
    mirror.  Regenerating the block must carry those mirrors over.
    """

    def test_parent_mirror_url_preserved_ahead_of_github(self):
        content = _block(
            urls=[
                f"{MIRROR}/OpenROAD-12345.tar.gz",
                "https://github.com/The-OpenROAD-Project/OpenROAD/archive/12345.tar.gz",
            ]
        )
        out = _regenerate(content)
        mirror_idx = out.find(f'"{MIRROR}/OpenROAD-67890.tar.gz"')
        github_idx = out.find(
            '"https://github.com/The-OpenROAD-Project/OpenROAD/archive/67890.tar.gz"'
        )
        self.assertNotEqual(mirror_idx, -1, "mirror URL was dropped")
        self.assertNotEqual(github_idx, -1, "GitHub URL was dropped")
        self.assertLess(mirror_idx, github_idx, "mirror must be tried first")
        self.assertNotIn("12345.tar.gz", out, "stale commit left in a URL")

    def test_parent_mirror_absent_keeps_single_url_line(self):
        out = _regenerate(_block())
        self.assertIn(
            'urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/'
            '67890.tar.gz"]',
            out,
        )

    def test_submodule_mirror_fetch_preserved_at_new_sha(self):
        fetch = (
            f"gsutil cp gs://example/abc-{OLD_SHA}-{OLD_HEX}.tar.gz "
            f".openroad-submodule-third-party-abc-{OLD_SHA}.tar.gz"
        )
        content = _block([_submodule_cmd("third-party/abc", fetch)])
        out = _regenerate(content)
        self.assertIn(f"gsutil cp gs://example/abc-{NEW_SHA}-{NEW_HEX}.tar.gz", out)
        self.assertNotIn(OLD_SHA, out, "stale sha left in the mirrored fetch")
        self.assertNotIn(OLD_HEX, out, "stale digest left in the mirrored fetch")

    def test_mirrored_submodule_still_verifies_its_digest(self):
        """The fetch is the consumer's; verify/extract/cleanup stay generated."""
        fetch = f"cp /mnt/mirror/abc-{OLD_SHA}.tar.gz stage.tar.gz"
        content = _block([_submodule_cmd("third-party/abc", fetch)])
        out = _regenerate(content)
        stagefile = f".openroad-submodule-third-party-abc-{NEW_SHA}.tar.gz"
        self.assertIn(f"echo '{NEW_HEX}  {stagefile}' | sha256sum -c -", out)
        self.assertIn(
            f"tar xzf {stagefile} --strip-components=1 -C third-party/abc", out
        )

    def test_mirrored_submodule_fetch_is_not_a_custom_patch_cmd(self):
        """It must not trip the "move your patches back" BumpError."""
        cmd = _submodule_cmd(
            "third-party/abc", f"gsutil cp gs://example/x-{OLD_SHA}.tar.gz s.tar.gz"
        )
        self.assertFalse(bump_impl._is_custom_patch_cmd(cmd))
        out = _regenerate(_block([cmd]))
        self.assertIn(f"gsutil cp gs://example/x-{NEW_SHA}.tar.gz", out)

    def test_genuinely_custom_patch_cmd_still_rejected(self):
        with self.assertRaises(bump_impl.BumpError):
            _regenerate(_block(["sed -i 's|foo|bar|' src/BUILD"]))

    def test_default_submodule_fetch_is_not_treated_as_a_mirror(self):
        content = _block([_submodule_cmd("third-party/abc")])
        self.assertEqual(bump_impl._parse_submodule_mirror_fetches(content), {})

    def test_submodule_sha_read_from_stagefile_not_url(self):
        """Digest reuse must work when the mirror URL doesn't name the sha."""
        cmd = _submodule_cmd(
            "third-party/abc", "gsutil cp gs://example/opaque-object s.tar.gz"
        )
        digests = bump_impl._parse_submodule_digests(_block([cmd]))
        self.assertEqual(digests["third-party/abc"], (OLD_SHA, OLD_HEX))


if __name__ == "__main__":
    unittest.main()
