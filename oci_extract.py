#!/usr/bin/env python3
"""Extract filesystem from Docker/OCI container images without Docker.

Two modes of operation:

  Standalone (downloads + extracts in one step):
    python oci_extract.py extract --image docker.io/openroad/orfs --digest <sha256> --output /path

  Bazel-integrated (three phases, enables Bazel repository cache for layers):
    1. python oci_extract.py resolve --image <image> --digest <sha256>
       → outputs JSON with layer digests and direct download URLs
    2. Bazel downloads each layer via repository_ctx.download(sha256=...)
       → unchanged layers across image versions are served from cache
    3. python oci_extract.py extract-layers --output /path --layers l0.tar.gz l1.tar.gz ...
       → extracts pre-downloaded tarballs with Docker whiteout handling

  Resolve tag to digest:
    python oci_extract.py digest --image docker.io/openroad/orfs --tag <tag>

The Bazel-integrated mode splits downloading from extraction so that
repository_ctx.download() handles each layer blob.  Bazel's repository
cache is content-addressed by SHA-256, so when an image is updated only
the layers whose digests actually changed are re-downloaded.  Docker
images share base layers across versions, so typically only a few top
layers change per release.

Stdlib-only (no pip dependencies) so it can run during Bazel repository rule phase.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlparse

MANIFEST_TYPES = ", ".join(
    [
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    ]
)

CHUNK_SIZE = 1 << 20  # 1 MiB


def parse_image(image_str):
    """Parse an image string into (registry, repository).

    Strips any tag or digest suffix from the repository component.

    Examples:
        docker.io/openroad/orfs:tag -> (registry-1.docker.io, openroad/orfs)
        docker.io/openroad/orfs -> (registry-1.docker.io, openroad/orfs)
        registry.example.com/foo/bar -> (registry.example.com, foo/bar)
        ubuntu -> (registry-1.docker.io, library/ubuntu)
    """
    # Strip digest (@sha256:...) first
    ref = image_str.split("@")[0]
    # Strip tag (:tag) from the last path component only,
    # so registry port (localhost:5000) is not affected.
    last_slash = ref.rfind("/")
    if last_slash >= 0:
        tail = ref[last_slash:]
        if ":" in tail:
            ref = ref[:last_slash] + tail.split(":")[0]
    else:
        # No slash at all (e.g. "ubuntu:22.04")
        if ":" in ref:
            ref = ref.split(":")[0]

    parts = ref.split("/", 1)
    if len(parts) == 1 or ("." not in parts[0] and ":" not in parts[0]):
        registry = "registry-1.docker.io"
        repository = ref if "/" in ref else "library/" + ref
    else:
        registry = parts[0]
        repository = parts[1]

    if registry in ("docker.io", "index.docker.io"):
        registry = "registry-1.docker.io"

    if registry == "registry-1.docker.io" and "/" not in repository:
        repository = "library/" + repository

    return registry, repository


def get_token(registry, repository):
    """Get an anonymous bearer token for pulling from the registry."""
    if registry != "registry-1.docker.io":
        return None

    url = (
        "https://auth.docker.io/token"
        f"?service=registry.docker.io&scope=repository:{repository}:pull"
    )
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    return data["token"]


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip Authorization header when redirected to a different host.

    Docker Hub redirects blob downloads to a CDN. Sending the
    registry bearer token to the CDN causes 400 errors.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        original_host = urlparse(req.full_url).hostname
        redirect_host = urlparse(newurl).hostname
        if original_host != redirect_host:
            new_req.remove_header("Authorization")
        return new_req


def _build_opener():
    return urllib.request.build_opener(_RedirectHandler)


def _registry_request(url, token, method="GET", accept=None):
    """Make an authenticated request to a container registry."""
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if accept:
        req.add_header("Accept", accept)
    opener = _build_opener()
    return opener.open(req)


def fetch_manifest(registry, repository, reference, token):
    """Fetch and return the image manifest as a dict.

    If the manifest is an OCI index (multi-arch), automatically
    selects the linux/amd64 manifest and re-fetches it.
    """
    url = f"https://{registry}/v2/{repository}/manifests/{reference}"
    with _registry_request(url, token, accept=MANIFEST_TYPES) as resp:
        body = resp.read()
        manifest = json.loads(body)

    media_type = manifest.get("mediaType", "")

    if (
        media_type
        in (
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
        )
        or "manifests" in manifest
    ):
        digest = _select_platform(manifest, "linux", "amd64")
        return fetch_manifest(registry, repository, digest, token)

    return manifest


def _select_platform(index, os_name, architecture):
    """Select a platform-specific manifest digest from an OCI index."""
    for entry in index.get("manifests", []):
        platform = entry.get("platform", {})
        if (
            platform.get("os") == os_name
            and platform.get("architecture") == architecture
        ):
            return entry["digest"]
    raise ValueError(
        f"No {os_name}/{architecture} manifest found in index. "
        f"Available: {[m.get('platform', {}) for m in index.get('manifests', [])]}"
    )


def resolve_digest(registry, repository, tag, token):
    """Resolve a tag to its manifest digest via HEAD request."""
    url = f"https://{registry}/v2/{repository}/manifests/{tag}"
    with _registry_request(url, token, method="HEAD", accept=MANIFEST_TYPES) as resp:
        digest = resp.headers.get("Docker-Content-Digest", "")
    if not digest:
        raise ValueError(f"No Docker-Content-Digest header for {repository}:{tag}")
    return digest


def download_blob(registry, repository, digest, token, dest_path):
    """Download a blob and verify its sha256 digest."""
    url = f"https://{registry}/v2/{repository}/blobs/{digest}"
    expected_hash = digest.split(":", 1)[-1]

    sha = hashlib.sha256()
    with _registry_request(url, token) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
            sha.update(chunk)

    actual_hash = sha.hexdigest()
    if actual_hash != expected_hash:
        os.unlink(dest_path)
        raise ValueError(
            f"SHA256 mismatch for {digest}: expected {expected_hash}, got {actual_hash}"
        )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Capture redirect Location without following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _RedirectCaptured(newurl)


class _RedirectCaptured(Exception):
    """Raised by _NoRedirectHandler to capture the redirect URL."""

    def __init__(self, url):
        self.url = url


def resolve_blob_url(registry, repository, digest, token):
    """Resolve a blob digest to a direct download URL.

    Docker Hub redirects blob requests to a CDN with a signed URL that
    requires no Authorization header.  This function captures that
    redirect target so that Bazel's repository_ctx.download() can fetch
    it directly (avoiding auth/redirect complications).

    For registries that don't redirect, returns the original blob URL.
    """
    url = f"https://{registry}/v2/{repository}/blobs/{digest}"
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        # If no redirect, the registry serves the blob directly.
        with opener.open(req) as resp:
            return url
    except _RedirectCaptured as e:
        return e.url
    except urllib.error.HTTPError:
        # Fall back to the original URL if anything goes wrong.
        return url


def resolve_layers(image, reference):
    """Resolve a container image to its layer digests and download URLs.

    Returns a list of dicts: [{"digest": "sha256:...", "size": N, "url": "https://..."}]
    """
    registry, repository = parse_image(image)
    token = get_token(registry, repository)
    manifest = fetch_manifest(registry, repository, reference, token)

    layers = manifest.get("layers", manifest.get("fsLayers", []))
    result = []
    for layer in layers:
        digest = layer.get("digest", layer.get("blobSum"))
        size = layer.get("size", 0)
        url = resolve_blob_url(registry, repository, digest, token)
        result.append({"digest": digest, "size": size, "url": url})

    return result


def extract_layers(layer_paths, output_dir):
    """Extract pre-downloaded layer tarballs into output_dir.

    Layers must be provided in order (bottom to top).  Handles Docker
    whiteout files (.wh.*) for proper layer stacking.
    """
    pigz = shutil.which("pigz")
    os.makedirs(output_dir, exist_ok=True)
    if pigz:
        print(f"Using pigz: {pigz}", file=sys.stderr)
    for i, path in enumerate(layer_paths):
        print(f"Extracting layer {i + 1}/{len(layer_paths)}: {path}", file=sys.stderr)
        extract_layer(path, output_dir, pigz=pigz)
    print(
        f"Extracted {len(layer_paths)} layers to {output_dir}",
        file=sys.stderr,
    )


def _open_tar(tar_path, pigz=None):
    """Open a compressed tarball for streaming extraction.

    When *pigz* is a path to the pigz binary, decompression is
    offloaded to that external process (parallel, much faster).
    Otherwise, Python's built-in gzip is used.

    Returns (tar, proc) where *proc* is the pigz subprocess
    (or None).  Caller must wait()/close proc after the tar
    context exits.
    """
    if pigz:
        proc = subprocess.Popen(
            [pigz, "-dc", tar_path],
            stdout=subprocess.PIPE,
        )
        tar = tarfile.open(fileobj=proc.stdout, mode="r|")
        return tar, proc
    return tarfile.open(tar_path, "r|gz"), None


def extract_layer(tar_path, output_dir, pigz=None):
    """Extract a single layer tarball, handling OCI whiteout files.

    Whiteout semantics (OCI image spec):
    - .wh.<name>: delete <name> in that directory
    - .wh..wh..opq: delete all prior contents of that directory
    """
    whiteouts = []
    opaque_dirs = []

    tar, proc = _open_tar(tar_path, pigz=pigz)
    with tar:
        for member in tar:
            dest = os.path.join(output_dir, member.name)
            real_dest = os.path.realpath(dest)
            real_output = os.path.realpath(output_dir)
            if (
                not real_dest.startswith(real_output + os.sep)
                and real_dest != real_output
            ):
                print(
                    f"WARNING: skipping path traversal: {member.name}", file=sys.stderr
                )
                continue

            basename = os.path.basename(member.name)
            dirname = os.path.dirname(member.name)

            if basename == ".wh..wh..opq":
                opaque_dirs.append(os.path.join(output_dir, dirname))
                continue

            if basename.startswith(".wh."):
                target_name = basename[4:]
                target_path = os.path.join(output_dir, dirname, target_name)
                whiteouts.append(target_path)
                continue

            try:
                tar.extract(member, output_dir, set_attrs=False)
                # set_attrs=False skips all permissions (to avoid uid/gid
                # issues), but we still need execute bits for binaries and
                # scripts.  Restore them from the tar member's mode.
                if member.isreg() and member.mode & 0o111:
                    dest_path = os.path.join(output_dir, member.name)
                    os.chmod(dest_path, os.stat(dest_path).st_mode | 0o111)
            except (OSError, tarfile.TarError) as e:
                print(f"WARNING: failed to extract {member.name}: {e}", file=sys.stderr)

    for opaque_dir in opaque_dirs:
        if os.path.isdir(opaque_dir):
            for entry in os.listdir(opaque_dir):
                entry_path = os.path.join(opaque_dir, entry)
                if os.path.isdir(entry_path) and not os.path.islink(entry_path):
                    shutil.rmtree(entry_path)
                else:
                    os.unlink(entry_path)

    for target in whiteouts:
        if os.path.exists(target) or os.path.islink(target):
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target)
            else:
                os.unlink(target)

    if proc is not None:
        proc.wait()


_PIGZ = shutil.which("pigz")


def extract_image(image, reference, output_dir):
    """Extract a container image filesystem to output_dir.

    Args:
        image: Image string like "docker.io/openroad/orfs"
        reference: Digest ("sha256:...") or tag
        output_dir: Directory to extract into
    """
    registry, repository = parse_image(image)
    print(f"Registry: {registry}, Repository: {repository}", file=sys.stderr)

    token = get_token(registry, repository)

    print(f"Fetching manifest for {reference}...", file=sys.stderr)
    manifest = fetch_manifest(registry, repository, reference, token)

    layers = manifest.get("layers", manifest.get("fsLayers", []))
    print(f"Image has {len(layers)} layers", file=sys.stderr)
    if _PIGZ:
        print(f"Using pigz: {_PIGZ}", file=sys.stderr)

    os.makedirs(output_dir, exist_ok=True)

    for i, layer in enumerate(layers):
        digest = layer.get("digest", layer.get("blobSum"))
        size = layer.get("size", 0)
        size_mb = size / (1024 * 1024) if size else 0
        print(
            f"Layer {i + 1}/{len(layers)}: " f"{digest[:30]}... ({size_mb:.1f} MB)",
            file=sys.stderr,
        )

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            download_blob(registry, repository, digest, token, tmp_path)
            extract_layer(tmp_path, output_dir, pigz=_PIGZ)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    print(
        f"Extracted {len(layers)} layers to {output_dir}",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(description="OCI image extractor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract image filesystem")
    extract_parser.add_argument(
        "--image", required=True, help="Image reference (e.g. docker.io/openroad/orfs)"
    )
    extract_parser.add_argument(
        "--digest", required=True, help="Image sha256 digest (without sha256: prefix)"
    )
    extract_parser.add_argument("--output", required=True, help="Output directory")

    resolve_parser = subparsers.add_parser(
        "resolve", help="Resolve image layers to direct download URLs"
    )
    resolve_parser.add_argument(
        "--image", required=True, help="Image reference (e.g. docker.io/openroad/orfs)"
    )
    resolve_parser.add_argument(
        "--digest", required=True, help="Image sha256 digest (without sha256: prefix)"
    )

    extract_layers_parser = subparsers.add_parser(
        "extract-layers", help="Extract pre-downloaded layer tarballs"
    )
    extract_layers_parser.add_argument(
        "--output", required=True, help="Output directory"
    )
    extract_layers_parser.add_argument(
        "--layers", required=True, nargs="+", help="Layer tarball paths in order"
    )

    digest_parser = subparsers.add_parser("digest", help="Resolve tag to digest")
    digest_parser.add_argument("--image", required=True, help="Image reference")
    digest_parser.add_argument("--tag", required=True, help="Image tag to resolve")

    args = parser.parse_args()

    if args.command == "extract":
        digest = args.digest
        if not digest.startswith("sha256:"):
            digest = "sha256:" + digest
        extract_image(args.image, digest, args.output)

    elif args.command == "resolve":
        digest = args.digest
        if not digest.startswith("sha256:"):
            digest = "sha256:" + digest
        layers = resolve_layers(args.image, digest)
        json.dump({"layers": layers}, sys.stdout)

    elif args.command == "extract-layers":
        extract_layers(args.layers, args.output)

    elif args.command == "digest":
        registry, repository = parse_image(args.image)
        token = get_token(registry, repository)
        digest = resolve_digest(registry, repository, args.tag, token)
        # Print just the hash for easy consumption
        print(digest.replace("sha256:", ""))


if __name__ == "__main__":
    main()
