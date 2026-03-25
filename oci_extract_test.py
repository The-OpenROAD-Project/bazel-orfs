#!/usr/bin/env python3
"""Unit tests for oci_extract.py"""

import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

import oci_extract


class TestParseImage(unittest.TestCase):
    def test_docker_hub_with_org(self):
        self.assertEqual(
            oci_extract.parse_image("docker.io/openroad/orfs"),
            ("registry-1.docker.io", "openroad/orfs"),
        )

    def test_docker_hub_shorthand(self):
        self.assertEqual(
            oci_extract.parse_image("openroad/orfs"),
            ("registry-1.docker.io", "openroad/orfs"),
        )

    def test_docker_hub_library_image(self):
        self.assertEqual(
            oci_extract.parse_image("ubuntu"),
            ("registry-1.docker.io", "library/ubuntu"),
        )

    def test_index_docker_io(self):
        self.assertEqual(
            oci_extract.parse_image(
                "index.docker.io/openroad/orfs"
            ),
            ("registry-1.docker.io", "openroad/orfs"),
        )

    def test_custom_registry(self):
        self.assertEqual(
            oci_extract.parse_image("ghcr.io/org/repo"),
            ("ghcr.io", "org/repo"),
        )

    def test_registry_with_port(self):
        self.assertEqual(
            oci_extract.parse_image("localhost:5000/myimage"),
            ("localhost:5000", "myimage"),
        )

    def test_strips_tag(self):
        """The actual CI failure: image string includes a tag."""
        self.assertEqual(
            oci_extract.parse_image(
                "docker.io/openroad/orfs:26Q1-656-g97416b2e4"
            ),
            ("registry-1.docker.io", "openroad/orfs"),
        )

    def test_strips_digest(self):
        self.assertEqual(
            oci_extract.parse_image(
                "docker.io/openroad/orfs@sha256:abc123"
            ),
            ("registry-1.docker.io", "openroad/orfs"),
        )

    def test_port_with_tag(self):
        """Port in registry must not be confused with tag."""
        self.assertEqual(
            oci_extract.parse_image(
                "localhost:5000/myimage:latest"
            ),
            ("localhost:5000", "myimage"),
        )

    def test_tag_with_shorthand(self):
        self.assertEqual(
            oci_extract.parse_image("openroad/orfs:v1.0"),
            ("registry-1.docker.io", "openroad/orfs"),
        )

    def test_library_image_with_tag(self):
        self.assertEqual(
            oci_extract.parse_image("ubuntu:22.04"),
            ("registry-1.docker.io", "library/ubuntu"),
        )

    def test_tag_and_digest_both_present(self):
        """docker.io/repo:tag@sha256:... — digest wins."""
        self.assertEqual(
            oci_extract.parse_image(
                "docker.io/openroad/orfs:v1@sha256:abc"
            ),
            ("registry-1.docker.io", "openroad/orfs"),
        )

    def test_deeply_nested_repo(self):
        self.assertEqual(
            oci_extract.parse_image(
                "ghcr.io/org/sub/repo:latest"
            ),
            ("ghcr.io", "org/sub/repo"),
        )


class TestGetToken(unittest.TestCase):
    @patch("oci_extract.urllib.request.urlopen")
    def test_docker_hub_token(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = (
            json.dumps({"token": "abc123"}).encode()
        )
        mock_resp.__enter__ = MagicMock(
            return_value=mock_resp
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        token = oci_extract.get_token(
            "registry-1.docker.io", "openroad/orfs"
        )
        self.assertEqual(token, "abc123")

        url = mock_urlopen.call_args[0][0]
        self.assertIn("repository:openroad/orfs:pull", url)

    def test_non_docker_hub_returns_none(self):
        self.assertIsNone(
            oci_extract.get_token("ghcr.io", "org/repo")
        )


class TestSelectPlatform(unittest.TestCase):
    def test_selects_linux_amd64(self):
        index = {
            "manifests": [
                {
                    "digest": "sha256:arm64digest",
                    "platform": {
                        "os": "linux",
                        "architecture": "arm64",
                    },
                },
                {
                    "digest": "sha256:amd64digest",
                    "platform": {
                        "os": "linux",
                        "architecture": "amd64",
                    },
                },
            ]
        }
        self.assertEqual(
            oci_extract._select_platform(
                index, "linux", "amd64"
            ),
            "sha256:amd64digest",
        )

    def test_raises_if_not_found(self):
        index = {
            "manifests": [
                {
                    "digest": "sha256:arm64",
                    "platform": {
                        "os": "linux",
                        "architecture": "arm64",
                    },
                },
            ]
        }
        with self.assertRaises(ValueError):
            oci_extract._select_platform(
                index, "linux", "amd64"
            )


class TestFetchManifest(unittest.TestCase):
    @patch("oci_extract._registry_request")
    def test_single_manifest(self, mock_request):
        manifest = {
            "mediaType": (
                "application/vnd.docker.distribution"
                ".manifest.v2+json"
            ),
            "layers": [
                {"digest": "sha256:abc", "size": 100}
            ],
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = (
            json.dumps(manifest).encode()
        )
        mock_resp.__enter__ = MagicMock(
            return_value=mock_resp
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_request.return_value = mock_resp

        result = oci_extract.fetch_manifest(
            "reg", "repo", "sha256:abc", "token"
        )
        self.assertEqual(
            result["layers"][0]["digest"], "sha256:abc"
        )

    @patch("oci_extract._registry_request")
    def test_multiarch_manifest(self, mock_request):
        index = {
            "mediaType": (
                "application/vnd.oci.image.index.v1+json"
            ),
            "manifests": [
                {
                    "digest": "sha256:arm",
                    "platform": {
                        "os": "linux",
                        "architecture": "arm64",
                    },
                },
                {
                    "digest": "sha256:amd",
                    "platform": {
                        "os": "linux",
                        "architecture": "amd64",
                    },
                },
            ],
        }
        single_manifest = {
            "mediaType": (
                "application/vnd.oci.image.manifest.v1+json"
            ),
            "layers": [
                {"digest": "sha256:layer1", "size": 200}
            ],
        }

        responses = []
        for data in [index, single_manifest]:
            mock_resp = MagicMock()
            mock_resp.read.return_value = (
                json.dumps(data).encode()
            )
            mock_resp.__enter__ = MagicMock(
                return_value=mock_resp
            )
            mock_resp.__exit__ = MagicMock(
                return_value=False
            )
            responses.append(mock_resp)

        mock_request.side_effect = responses

        result = oci_extract.fetch_manifest(
            "reg", "repo", "tag", "token"
        )
        self.assertEqual(
            result["layers"][0]["digest"], "sha256:layer1"
        )
        # Second call should be for the amd64 digest
        second_url = mock_request.call_args_list[1][0][0]
        self.assertIn("sha256:amd", second_url)


class TestResolveDigest(unittest.TestCase):
    @patch("oci_extract._registry_request")
    def test_resolve(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.headers = {
            "Docker-Content-Digest": "sha256:deadbeef"
        }
        mock_resp.__enter__ = MagicMock(
            return_value=mock_resp
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_request.return_value = mock_resp

        digest = oci_extract.resolve_digest(
            "reg", "repo", "latest", "token"
        )
        self.assertEqual(digest, "sha256:deadbeef")

    @patch("oci_extract._registry_request")
    def test_missing_header(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.headers = {}
        mock_resp.__enter__ = MagicMock(
            return_value=mock_resp
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_request.return_value = mock_resp

        with self.assertRaises(ValueError):
            oci_extract.resolve_digest(
                "reg", "repo", "latest", "token"
            )


class TestDownloadBlob(unittest.TestCase):
    @patch("oci_extract._registry_request")
    def test_successful_download(self, mock_request):
        content = b"hello world blob"
        expected_hash = hashlib.sha256(content).hexdigest()
        digest = f"sha256:{expected_hash}"

        mock_resp = MagicMock()
        mock_resp.read = MagicMock(
            side_effect=[content, b""]
        )
        mock_resp.__enter__ = MagicMock(
            return_value=mock_resp
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_request.return_value = mock_resp

        with tempfile.NamedTemporaryFile(delete=False) as f:
            dest = f.name
        try:
            oci_extract.download_blob(
                "reg", "repo", digest, "token", dest
            )
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), content)
        finally:
            os.unlink(dest)

    @patch("oci_extract._registry_request")
    def test_sha256_mismatch(self, mock_request):
        content = b"hello world blob"
        digest = (
            "sha256:"
            "0000000000000000000000000000000000000000"
            "000000000000000000000000"
        )

        mock_resp = MagicMock()
        mock_resp.read = MagicMock(
            side_effect=[content, b""]
        )
        mock_resp.__enter__ = MagicMock(
            return_value=mock_resp
        )
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_request.return_value = mock_resp

        with tempfile.NamedTemporaryFile(delete=False) as f:
            dest = f.name
        try:
            with self.assertRaises(ValueError) as ctx:
                oci_extract.download_blob(
                    "reg", "repo", digest, "token", dest
                )
            self.assertIn(
                "SHA256 mismatch", str(ctx.exception)
            )
            self.assertFalse(os.path.exists(dest))
        finally:
            if os.path.exists(dest):
                os.unlink(dest)


class TestExtractLayer(unittest.TestCase):
    def setUp(self):
        self.output_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def _make_tar(self, members):
        """Create a tar with given (name, content) tuples.

        content=None for directories.
        """
        tar_path = os.path.join(
            self.output_dir, "_layer.tar"
        )
        with tarfile.open(tar_path, "w:gz") as tar:
            for name, content in members:
                if content is None:
                    info = tarfile.TarInfo(name=name)
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    tar.addfile(info)
                else:
                    info = tarfile.TarInfo(name=name)
                    info.size = len(content)
                    tar.addfile(
                        info, io.BytesIO(content)
                    )
        return tar_path

    def test_basic_extraction(self):
        tar_path = self._make_tar(
            [("hello.txt", b"world")]
        )
        extract_dir = os.path.join(
            self.output_dir, "extract"
        )
        os.makedirs(extract_dir)
        oci_extract.extract_layer(tar_path, extract_dir)
        path = os.path.join(extract_dir, "hello.txt")
        with open(path) as f:
            self.assertEqual(f.read(), "world")

    def test_whiteout_file(self):
        extract_dir = os.path.join(
            self.output_dir, "extract"
        )
        os.makedirs(extract_dir)
        target = os.path.join(extract_dir, "deleteme.txt")
        with open(target, "w") as f:
            f.write("gone")

        tar_path = self._make_tar(
            [(".wh.deleteme.txt", b"")]
        )
        oci_extract.extract_layer(tar_path, extract_dir)
        self.assertFalse(os.path.exists(target))

    def test_whiteout_directory(self):
        extract_dir = os.path.join(
            self.output_dir, "extract"
        )
        subdir = os.path.join(extract_dir, "subdir")
        os.makedirs(subdir, exist_ok=True)
        with open(os.path.join(subdir, "file.txt"), "w") as f:
            f.write("content")

        tar_path = self._make_tar(
            [(".wh.subdir", b"")]
        )
        oci_extract.extract_layer(tar_path, extract_dir)
        self.assertFalse(os.path.exists(subdir))

    def test_opaque_whiteout(self):
        extract_dir = os.path.join(
            self.output_dir, "extract"
        )
        subdir = os.path.join(extract_dir, "mydir")
        os.makedirs(subdir, exist_ok=True)
        with open(os.path.join(subdir, "old.txt"), "w") as f:
            f.write("old content")

        tar_path = self._make_tar(
            [("mydir/.wh..wh..opq", b"")]
        )
        oci_extract.extract_layer(tar_path, extract_dir)
        self.assertTrue(os.path.isdir(subdir))
        self.assertEqual(os.listdir(subdir), [])

    def test_layer_ordering(self):
        """Later layer overwrites earlier layer's files."""
        extract_dir = os.path.join(
            self.output_dir, "extract"
        )
        os.makedirs(extract_dir)

        tar1 = self._make_tar(
            [("file.txt", b"version1")]
        )
        tar2_path = os.path.join(
            self.output_dir, "_layer2.tar"
        )
        with tarfile.open(tar2_path, "w:gz") as tar:
            info = tarfile.TarInfo(name="file.txt")
            content = b"version2"
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

        oci_extract.extract_layer(tar1, extract_dir)
        oci_extract.extract_layer(tar2_path, extract_dir)

        path = os.path.join(extract_dir, "file.txt")
        with open(path) as f:
            self.assertEqual(f.read(), "version2")

    def test_path_traversal_rejected(self):
        extract_dir = os.path.join(
            self.output_dir, "extract"
        )
        os.makedirs(extract_dir)

        tar_path = os.path.join(
            self.output_dir, "_evil.tar"
        )
        with tarfile.open(tar_path, "w:gz") as tar:
            info = tarfile.TarInfo(
                name="../../etc/passwd"
            )
            content = b"evil"
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

        oci_extract.extract_layer(tar_path, extract_dir)
        evil = os.path.join(
            extract_dir, "../../etc/passwd"
        )
        self.assertFalse(os.path.exists(evil))


class TestRedirectHandler(unittest.TestCase):
    def test_strips_auth_on_cross_host_redirect(self):
        handler = oci_extract._RedirectHandler()
        url = (
            "https://registry-1.docker.io"
            "/v2/repo/blobs/sha256:abc"
        )
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer token123")

        cdn_url = "https://cdn.example.com/blob"
        with patch.object(
            urllib.request.HTTPRedirectHandler,
            "redirect_request",
        ) as mock_super:
            new_req = MagicMock()
            new_req.full_url = cdn_url
            mock_super.return_value = new_req

            result = handler.redirect_request(
                req, None, 302, "Found", {}, cdn_url
            )
            result.remove_header.assert_called_with(
                "Authorization"
            )

    def test_keeps_auth_on_same_host_redirect(self):
        handler = oci_extract._RedirectHandler()
        url = (
            "https://registry-1.docker.io"
            "/v2/repo/blobs/sha256:abc"
        )
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer token123")

        same_url = (
            "https://registry-1.docker.io/v2/other"
        )
        with patch.object(
            urllib.request.HTTPRedirectHandler,
            "redirect_request",
        ) as mock_super:
            new_req = MagicMock()
            new_req.full_url = same_url
            mock_super.return_value = new_req

            result = handler.redirect_request(
                req, None, 302, "Found", {}, same_url
            )
            result.remove_header.assert_not_called()


class TestExtractImageE2E(unittest.TestCase):
    """End-to-end test with all HTTP mocked."""

    @patch("oci_extract.download_blob")
    @patch("oci_extract.fetch_manifest")
    @patch("oci_extract.get_token")
    def test_extract_image(
        self, mock_token, mock_manifest, mock_download
    ):
        mock_token.return_value = "token"
        mock_manifest.return_value = {
            "mediaType": (
                "application/vnd.docker.distribution"
                ".manifest.v2+json"
            ),
            "layers": [
                {"digest": "sha256:aaa", "size": 100},
                {"digest": "sha256:bbb", "size": 200},
            ],
        }

        output_dir = tempfile.mkdtemp()
        try:

            def fake_download(
                reg, repo, digest, token, dest
            ):
                if "aaa" in digest:
                    members = [
                        ("base.txt", b"base content")
                    ]
                else:
                    members = [
                        ("overlay.txt", b"overlay")
                    ]

                with tarfile.open(dest, "w:gz") as tar:
                    for name, data in members:
                        info = tarfile.TarInfo(name=name)
                        info.size = len(data)
                        tar.addfile(
                            info, io.BytesIO(data)
                        )

            mock_download.side_effect = fake_download

            oci_extract.extract_image(
                "docker.io/openroad/orfs",
                "sha256:abc123",
                output_dir,
            )

            base = os.path.join(output_dir, "base.txt")
            overlay = os.path.join(
                output_dir, "overlay.txt"
            )
            self.assertTrue(os.path.exists(base))
            self.assertTrue(os.path.exists(overlay))
        finally:
            shutil.rmtree(output_dir)

    @patch("oci_extract.download_blob")
    @patch("oci_extract.fetch_manifest")
    @patch("oci_extract.get_token")
    def test_extract_image_with_tagged_ref(
        self, mock_token, mock_manifest, mock_download
    ):
        """Reproduce CI failure: image has tag in name."""
        mock_token.return_value = "token"
        mock_manifest.return_value = {
            "mediaType": (
                "application/vnd.docker.distribution"
                ".manifest.v2+json"
            ),
            "layers": [
                {"digest": "sha256:aaa", "size": 100},
            ],
        }

        def fake_download(reg, repo, digest, token, dest):
            with tarfile.open(dest, "w:gz") as tar:
                info = tarfile.TarInfo(name="f.txt")
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))

        mock_download.side_effect = fake_download

        output_dir = tempfile.mkdtemp()
        try:
            oci_extract.extract_image(
                "docker.io/openroad/orfs:26Q1-tag",
                "sha256:abc123",
                output_dir,
            )
            # Verify token was requested for the
            # repository without the tag
            mock_token.assert_called_with(
                "registry-1.docker.io", "openroad/orfs"
            )
        finally:
            shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
