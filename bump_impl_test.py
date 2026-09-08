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


REHASH_HEX = "e" * 64

SUBMODULE_PATHS = [path for path, _ in bump_impl.OPENROAD_SUBMODULES]


class TestSubmoduleDigestStability(unittest.TestCase):
    """A submodule's digest may not move unless its sha moves.

    GitHub's archives are not byte-stable, so re-hashing an unchanged
    submodule can hand back a different digest for identical content.  That
    breaks a consumer mirror keyed by digest outright, and it costs the
    digest its meaning: a mismatch should say the content changed.
    """

    def _regenerate(self, content, sha256_fn, sub_sha=OLD_SHA):
        return bump_impl.update_openroad_archive_override(
            content=content,
            openroad_commit="67890",
            fetch_integrity_fn=lambda u: "sha256-bar",
            fetch_sha256_hex_fn=sha256_fn,
            fetch_submodule_sha_fn=lambda r, c, p: sub_sha,
            workspace_dir=None,
        )

    def test_unchanged_submodule_sha_keeps_its_digest(self):
        content = _block([_submodule_cmd(path) for path in SUBMODULE_PATHS])
        out = self._regenerate(content, lambda u: REHASH_HEX)
        self.assertIn(OLD_HEX, out)
        self.assertNotIn(REHASH_HEX, out)

    def test_unchanged_submodule_is_not_re_downloaded(self):
        """The parent commit moving is not a reason to re-fetch every tarball."""
        content = _block([_submodule_cmd(path) for path in SUBMODULE_PATHS])
        urls = []

        def spy(url):
            urls.append(url)
            return REHASH_HEX

        self._regenerate(content, spy)
        self.assertEqual(urls, [], "re-hashed a submodule whose sha did not move")

    def test_changed_submodule_sha_is_still_rehashed(self):
        """Reuse is keyed on the sha, so a moved submodule must not be cached."""
        out = self._regenerate(
            _block([_submodule_cmd("third-party/abc")]),
            lambda u: NEW_HEX,
            sub_sha=NEW_SHA,
        )
        self.assertIn(NEW_HEX, out)
        self.assertNotIn(OLD_HEX, out)


class TestUpdateOrfsSourceTag(unittest.TestCase):
    """ORFS as an extension-created http_archive.

    `patches` on an override is honoured only from the root module, so
    ORFS is fetched by bazel-orfs's module extension and the root picks
    the version with an orfs.source() tag. The bumper has to rewrite that
    shape as well as the two archive_override shapes.
    """

    CONTENT = """orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")

# Rewritten by //:bump.
orfs.source(
    commit = "427bd762b7b7448f8bb6bc4e14207aa3963fca30",
    integrity = "sha256-old",
)

orfs.default(
    yosys_plugins = ["@sv-elab//src/yosys_plugin:slang.so"],
)
"""

    @staticmethod
    def _integrity(url):
        return "sha256-new"

    def test_rewrites_commit_and_integrity(self):
        new = bump_impl.update_orfs_source_tag(
            self.CONTENT,
            "8c0616910615e843780ba527526f2b83a564ba70",
            fetch_integrity_fn=self._integrity,
        )
        self.assertIn(
            'commit = "8c0616910615e843780ba527526f2b83a564ba70"',
            new,
        )
        self.assertIn('integrity = "sha256-new"', new)
        self.assertNotIn("427bd762", new)
        self.assertNotIn("sha256-old", new)

    def test_leaves_the_default_tag_alone(self):
        # orfs.default() sits right after orfs.source() and must not be
        # swept into the rewritten span.
        new = bump_impl.update_orfs_source_tag(
            self.CONTENT,
            "8c0616910615e843780ba527526f2b83a564ba70",
            fetch_integrity_fn=self._integrity,
        )
        self.assertIn(
            'yosys_plugins = ["@sv-elab//src/yosys_plugin:slang.so"]',
            new,
        )
        self.assertIn("orfs.default(", new)

    def test_same_commit_skips_the_download(self):
        def explode(url):
            raise AssertionError("re-hashed a tarball already pinned")

        new = bump_impl.update_orfs_source_tag(
            self.CONTENT,
            "427bd762b7b7448f8bb6bc4e14207aa3963fca30",
            fetch_integrity_fn=explode,
        )
        self.assertEqual(new, self.CONTENT)

    def test_absent_tag_is_a_no_op(self):
        content = 'bazel_dep(name = "orfs")\n'
        self.assertIsNone(bump_impl.find_orfs_source_tag(content))
        self.assertEqual(
            bump_impl.update_orfs_source_tag(
                content,
                "8c0616910615e843780ba527526f2b83a564ba70",
                fetch_integrity_fn=self._integrity,
            ),
            content,
        )

    def test_commented_out_tag_is_not_found(self):
        content = '# orfs.source(commit = "dead", integrity = "sha256-x")\n'
        self.assertIsNone(bump_impl.find_orfs_source_tag(content))


if __name__ == "__main__":
    unittest.main()


class TestOrfsPatchPairing(unittest.TestCase):
    ORFS_SOURCE = """ORFS_BAZEL_PLATFORMS = ["asap7"]

ORFS_PATCHES = [
    Label("//patches:0037-single-writer.patch"),
    # a comment between entries
    Label("//patches:0047-export-flow-tcl.patch"),
    Label("//:root-level.patch"),
]

OTHER = [Label("//patches:not-an-orfs-patch.patch")]
"""

    FLOW_BUILD = 'exports_files(\n    ["scripts/synth.tcl", "scripts/flow.tcl"],\n)\n'

    EXPORT_PATCH = """diff --git a/flow/BUILD b/flow/BUILD
--- a/flow/BUILD
+++ b/flow/BUILD
@@ -1,3 +1,3 @@
 exports_files(
-    ["scripts/synth.tcl", "scripts/flow.tcl"],
+    ["scripts/synth.tcl", "scripts/flow.tcl", "scripts/variables.yaml"],
 )
"""

    def test_parse_orfs_patch_labels_reads_only_the_list(self):
        self.assertEqual(
            bump_impl.parse_orfs_patch_labels(self.ORFS_SOURCE),
            [
                "patches/0037-single-writer.patch",
                "patches/0047-export-flow-tcl.patch",
                "root-level.patch",
            ],
        )
        self.assertEqual(bump_impl.parse_orfs_patch_labels("X = 1\n"), [])

    def test_parse_unified_diff_uses_old_counts_and_marks_creation(self):
        patch = (
            "--- a/x.txt\n+++ b/x.txt\n@@ -1,3 +1,2 @@\n one\n--- dashes\n-three\n"
            "+new\n--- /dev/null\n+++ b/made.txt\n@@ -0,0 +1 @@\n+hello\n"
        )
        files = bump_impl.parse_unified_diff(patch)
        self.assertEqual(
            files,
            [
                ("x.txt", False, [("@@ -1,3 +1,2 @@", ["one", "-- dashes", "three"])]),
                ("made.txt", True, [("@@ -0,0 +1 @@", [])]),
            ],
        )

    def test_clean_patch_reports_nothing(self):
        tree = {"flow/BUILD": self.FLOW_BUILD}
        self.assertEqual(
            bump_impl.check_patch_against_tree("p.patch", self.EXPORT_PATCH, tree.get),
            [],
        )

    def test_deleted_file_is_named(self):
        problems = bump_impl.check_patch_against_tree(
            "patches/0047-export-flow-tcl.patch", self.EXPORT_PATCH, {}.get
        )
        self.assertEqual(
            problems,
            ["patches/0047-export-flow-tcl.patch: flow/BUILD does not exist"],
        )

    def test_moved_context_is_named_by_hunk(self):
        tree = {"flow/BUILD": 'exports_files(["scripts/other.tcl"])\n'}
        problems = bump_impl.check_patch_against_tree(
            "p.patch", self.EXPORT_PATCH, tree.get
        )
        self.assertEqual(
            problems, ["p.patch: flow/BUILD: hunk @@ -1,3 +1,3 @@ does not match"]
        )

    def test_creation_patch_needs_the_file_absent(self):
        patch = "--- /dev/null\n+++ b/new.tcl\n@@ -0,0 +1 @@\n+puts hi\n"
        self.assertEqual(bump_impl.check_patch_against_tree("p", patch, {}.get), [])
        self.assertEqual(
            bump_impl.check_patch_against_tree("p", patch, {"new.tcl": "x\n"}.get),
            ["p: creates new.tcl, which already exists"],
        )

    def test_check_orfs_patches_walks_the_list(self):
        bazel_orfs = {
            bump_impl.ORFS_SOURCE_BZL: self.ORFS_SOURCE,
            "patches/0037-single-writer.patch": self.EXPORT_PATCH,
            "patches/0047-export-flow-tcl.patch": self.EXPORT_PATCH,
        }
        orfs = {"flow/BUILD": self.FLOW_BUILD}
        self.assertEqual(
            bump_impl.check_orfs_patches(bazel_orfs.get, orfs.get),
            ["root-level.patch: named in ORFS_PATCHES but not in bazel-orfs"],
        )
        self.assertEqual(
            bump_impl.check_orfs_patches(bazel_orfs.get, {}.get),
            [
                "patches/0037-single-writer.patch: flow/BUILD does not exist",
                "patches/0047-export-flow-tcl.patch: flow/BUILD does not exist",
                "root-level.patch: named in ORFS_PATCHES but not in bazel-orfs",
            ],
        )
        self.assertEqual(
            bump_impl.check_orfs_patches({}.get, orfs.get),
            ["orfs_source.bzl not found in bazel-orfs; cannot check ORFS_PATCHES"],
        )

    def test_verify_raises_with_patch_and_commit_or_warns_under_ignore(self):
        bazel_orfs = {
            bump_impl.ORFS_SOURCE_BZL: 'ORFS_PATCHES = [\n    Label("//patches:0047.patch"),\n]\n',
            "patches/0047.patch": self.EXPORT_PATCH,
        }
        with self.assertRaises(bump_impl.BumpError) as ctx:
            bump_impl.verify_orfs_patch_pairing(
                "a71b115b9b7b95fc843e715bdebd557147ef98fc",
                bazel_orfs.get,
                {}.get,
                "bazel-orfs a668099ef676",
            )
        msg = str(ctx.exception)
        self.assertIn("bazel-orfs a668099ef676", msg)
        self.assertIn("ORFS a71b115b9b7b", msg)
        self.assertIn("patches/0047.patch: flow/BUILD does not exist", msg)
        self.assertIn("--ignore", msg)
        problems = bump_impl.verify_orfs_patch_pairing(
            "a71b115b9b7b95fc843e715bdebd557147ef98fc",
            bazel_orfs.get,
            {}.get,
            "bazel-orfs a668099ef676",
            ignore_errors=True,
        )
        self.assertEqual(problems, ["patches/0047.patch: flow/BUILD does not exist"])
        self.assertEqual(
            bump_impl.verify_orfs_patch_pairing(
                "a71b115b9b7b95fc843e715bdebd557147ef98fc",
                bazel_orfs.get,
                {"flow/BUILD": self.FLOW_BUILD}.get,
                "bazel-orfs a668099ef676",
            ),
            [],
        )
