"""Repository rules for extracting file trees from Docker container images.

Layer caching architecture
--------------------------
Docker images are composed of stacked layers, each identified by a SHA-256
digest.  When an image is updated (e.g. a new ORFS release), typically only
the top few layers change — base OS and library layers keep the same digests.

To exploit this, extraction is split into three phases:

  1. **Resolve** — a Python script fetches the image manifest and resolves
     each layer's blob URL.  Docker Hub redirects blob requests to a CDN
     with a signed, self-authenticating URL, so we capture that redirect
     target to avoid passing registry auth tokens through Bazel's downloader.

  2. **Download** — Bazel's ``repository_ctx.download(sha256=...)`` fetches
     each layer blob.  Bazel's repository cache is content-addressed, so
     layers whose digest hasn't changed since the last fetch are served
     from cache instantly — no HTTP request at all.  The ``setup-bazel``
     GitHub Action already persists this cache in CI
     (``repository-cache: true``).

  3. **Extract** — a Python script extracts the downloaded tarballs in layer
     order with Docker whiteout handling (.wh.* files).

If you are debugging download failures from a non-Docker-Hub registry,
note that phase 1 assumes the registry either: (a) redirects blob GETs
to a CDN (Docker Hub), or (b) serves blobs directly at the /v2/ URL
without authentication (public images on ghcr.io, quay.io, etc.).
Authenticated private registries may need additional handling in
``resolve_blob_url()`` in ``oci_extract.py``.
"""

load("@bazel_tools//tools/build_defs/repo:utils.bzl", "patch")

def _impl(repository_ctx):
    python = repository_ctx.path(repository_ctx.attr._python).realpath
    oci_extract = repository_ctx.path(repository_ctx.attr._oci_extract).realpath
    root = str(repository_ctx.path("."))

    # Phase 1: Resolve manifest → layer metadata with direct download URLs.
    resolve_result = repository_ctx.execute([
        python,
        oci_extract,
        "resolve",
        "--image",
        repository_ctx.attr.image,
        "--digest",
        repository_ctx.attr.sha256,
    ])
    if resolve_result.return_code != 0:
        fail(
            "Failed to resolve {}: {}".format(
                repository_ctx.attr.image,
                resolve_result.stderr,
            ),
        )

    manifest = json.decode(resolve_result.stdout)
    layers = manifest["layers"]
    repository_ctx.report_progress(
        "Resolved {} layers for {}.".format(len(layers), repository_ctx.attr.image),
    )

    # Phase 2: Download each layer via Bazel's downloader.
    # Bazel's repository cache is keyed by sha256, so unchanged layers
    # between image versions are served from cache (no HTTP request).
    layer_paths = []
    for i, layer in enumerate(layers):
        digest = layer["digest"]
        digest_hash = digest.split(":", 1)[-1]
        size_mb = layer.get("size", 0) / (1024 * 1024)
        filename = "layer_{}.tar.gz".format(i)

        repository_ctx.report_progress(
            "Downloading layer {}/{}: {}... ({:.1f} MB)".format(
                i + 1,
                len(layers),
                digest[:30],
                size_mb,
            ),
        )
        repository_ctx.download(
            url = layer["url"],
            output = filename,
            sha256 = digest_hash,
        )
        layer_paths.append(filename)

    # Phase 3: Extract all downloaded layers with whiteout handling.
    extract_args = [python, oci_extract, "extract-layers", "--output", root, "--layers"] + layer_paths
    extract_result = repository_ctx.execute(extract_args)
    if extract_result.return_code != 0:
        fail(
            "Failed to extract layers for {}: {}".format(
                repository_ctx.attr.image,
                extract_result.stderr,
            ),
        )

    # Clean up downloaded layer tarballs.
    for path in layer_paths:
        repository_ctx.delete(path)

    repository_ctx.report_progress("Extracted {}.".format(repository_ctx.attr.image))

    patcher = repository_ctx.path(repository_ctx.attr._patcher).realpath
    patcher_result = repository_ctx.execute(
        [
            python,
            patcher,
            repository_ctx.path("."),
        ],
    )
    if patcher_result.return_code != 0:
        fail(
            "Failed to run {}:".format(repository_ctx.attr._patcher),
            patcher_result.stderr,
        )

    repository_ctx.report_progress(
        "Created ld-linux wrappers for {}.".format(repository_ctx.attr.image),
    )

    repository_ctx.symlink(repository_ctx.attr.build_file, "BUILD")
    patch(repository_ctx)

docker_pkg = repository_rule(
    implementation = _impl,
    attrs = {
        "build_file": attr.label(mandatory = True),
        "image": attr.string(mandatory = True),
        "patch_args": attr.string_list(default = ["-p0"]),
        "patch_cmds": attr.string_list(default = []),
        "patch_cmds_win": attr.string_list(default = []),
        "patch_tool": attr.string(default = ""),
        "patches": attr.label_list(default = []),
        "sha256": attr.string(mandatory = False),
        "timeout": attr.int(default = 600),
        "_oci_extract": attr.label(
            doc = "OCI image extraction script.",
            default = Label("//:oci_extract.py"),
            allow_single_file = True,
        ),
        "_python": attr.label(
            doc = "Hermetic Python interpreter.",
            default = Label("@python_3_13_host//:python"),
            executable = True,
            cfg = "exec",
        ),
        "_patcher": attr.label(
            doc = "Python script to create ld-linux wrapper scripts.",
            default = Label("//:patcher.py"),
            allow_single_file = True,
        ),
    },
)
