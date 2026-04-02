# Docker Image Extraction

How bazel-orfs extracts the ORFS Docker image into a Bazel repository,
and the optimizations that have been applied.

## Architecture

The `docker_pkg` repository rule (in `docker.bzl`) extracts a Docker
image into a Bazel external repository in three phases:

### Phase 1: Resolve

`oci_extract.py download-plan` fetches the image manifest from the
registry and resolves each layer's blob URL.  Docker Hub redirects blob
requests to a CDN with a signed, self-authenticating URL.  The resolve
phase captures that redirect target so that Bazel's downloader can fetch
it without needing registry auth tokens.

All JSON parsing, digest extraction, and filename generation happens in
Python (unit-tested), so `docker.bzl` stays a thin shim.

### Phase 2: Download

Bazel's `repository_ctx.download(sha256=...)` fetches each layer blob.
Bazel's repository cache is content-addressed by SHA-256: if a layer
with the same digest was downloaded before, it is served from cache
instantly with no HTTP request.

Docker images are composed of stacked layers.  When an image is updated
(e.g. a new ORFS release), typically only the top few layers change —
base OS and library layers keep the same digests.  This means most
layers are cache hits on image updates, and only the changed layers are
re-downloaded.

The `setup-bazel` GitHub Action already persists the repository cache in
CI (`repository-cache: true`), so this is zero-configuration.

### Phase 3: Extract

`oci_extract.py extract-layers` extracts the downloaded tarballs in
layer order with Docker whiteout handling (`.wh.*` files).  Uses `pigz`
for parallel gzip decompression when available.

## Requirements

Requires Bazel 8+.  Only tested on Bazel 8.  Older versions may lack
`repository_ctx.download(sha256=...)` caching or `repository_ctx.delete()`.

## Performance history

Measurements taken against the ORFS image (21 layers, ~1.5 GB compressed).

| Optimization | Measured impact | Status | Notes |
|---|---|---|---|
| Streaming tar (`r\|gz` mode) | 72 s → 55 s (−23%) | Shipped | Replaced `getmembers()` O(n^2) with streaming O(n) |
| pigz parallel gzip | 55 s → 53 s (−4%) | Shipped | Opportunistic — detected at runtime via `shutil.which` |
| 1 MiB download chunks | 53 s → 52 s (−2%) | Shipped | Reduced syscall overhead (was 64 KiB) |
| Layer caching via `repository_ctx.download()` | 119 s → 25 s warm (−79%) | Shipped | Zero-config; uses Bazel repository cache |
| Parallel URL resolution | 8.2 s → 1.9 s (−77%) | Shipped | ThreadPoolExecutor for 21 concurrent redirect captures |
| Pipeline download → extract | Deadlocks | Failed | Pipe buffer deadlock between network writer and tar reader |
| Parallel layer downloads | N/A | Blocked | `repository_ctx.download()` is sequential in Starlark |
| zstd-compressed layers | Est. 3–5x faster decompress | Blocked | Docker Hub does not serve zstd layers for this image |
| Skip resolve on cache hit | Not impactful | Skipped | Resolve only runs when repo rule runs (cache miss); ~2 s with parallel resolution |

## De-featuring priority

Prioritized list of what to remove first if something breaks in
production, ordered by risk-to-benefit ratio (remove highest risk /
lowest benefit first):

| Priority | Feature | Risk | Benefit | Recommendation |
|---|---|---|---|---|
| 1 | pigz support | Medium — runtime detection, subprocess pipes, untestable in CI without pigz | −4% (2 s) | Remove first. Tiny gain, adds code paths. Python gzip works fine. |
| 2 | Parallel URL resolution | Low — stdlib ThreadPoolExecutor, well-tested | −77% of resolve phase (6 s) | Keep unless thread bugs surface. Easy to revert to sequential loop. |
| 3 | `download-plan` command | None — pure refactor, more testable | Testability | Keep. Strictly better than inline Starlark logic. |
| 4 | Layer caching (3-phase split) | Low — relies on stable Bazel APIs | −79% warm (94 s) | Core feature. Only remove if `repository_ctx.download()` breaks. |
| 5 | Streaming tar (`r\|gz` mode) | None — standard Python tarfile API | −23% (17 s) | Never remove. No downside. |

## Debugging

### Non-Docker-Hub registries

Phase 1 (`resolve_blob_url()` in `oci_extract.py`) assumes the registry
either:

- **(a)** Redirects blob GETs to a CDN (Docker Hub behavior), or
- **(b)** Serves blobs directly at the `/v2/` URL without authentication
  (public images on ghcr.io, quay.io, etc.)

Authenticated private registries may need additional handling in
`resolve_blob_url()`.

### CDN URL expiry

Docker Hub CDN URLs are signed and expire after ~15 minutes.  This is
not a problem because:

- URLs are resolved fresh each time the repository rule runs.
- Cached layers are served by Bazel's repository cache (keyed by
  SHA-256), so the URL is never used for cache hits.

### Inspecting the layer cache

```bash
ls $(bazel info repository_cache)/content_addressable/sha256/
```

### SSL certificates (NixOS, non-FHS systems)

`oci_extract.py` auto-detects the system CA certificate bundle at startup.
The detection order is:

1. `SSL_CERT_FILE` environment variable (if already set, used as-is)
2. `NIX_SSL_CERT_FILE` environment variable (NixOS)
3. Common distro paths: `/etc/ssl/certs/ca-certificates.crt` (Debian),
   `/etc/pki/tls/certs/ca-bundle.crt` (RHEL), etc.

This is needed because rules_python's hermetic Python bundles its own
OpenSSL, which looks for certificates at a compiled-in FHS path that
may not exist on NixOS or other non-standard layouts.

To override, set `SSL_CERT_FILE` in your environment before running Bazel.

### Diagnostic toggles

Environment variables to disable specific features for troubleshooting.
All default to `1` (enabled); set to `0` to disable.

| Variable | Effect when `=0` |
|---|---|
| `OCI_EXTRACT_SSL_SETUP` | Skip CA bundle auto-detection |
| `OCI_EXTRACT_PIGZ` | Use Python gzip instead of pigz |
| `OCI_EXTRACT_PARALLEL` | Sequential URL resolution (no threads) |

Example: `OCI_EXTRACT_PARALLEL=0 bazelisk fetch @docker_orfs//...`

### Standalone mode

`oci_extract.py extract` still works as a standalone one-step command
(download + extract) for use outside Bazel.  The three-phase split is
only used by the `docker_pkg` repository rule.
