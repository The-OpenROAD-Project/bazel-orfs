# Docker Image Extraction

How bazel-orfs extracts the ORFS Docker image into a Bazel repository,
and the optimizations that have been applied.

## Architecture

The `docker_pkg` repository rule (in `docker.bzl`) extracts a Docker
image into a Bazel external repository in three phases:

### Phase 1: Resolve

`oci_extract.py resolve` fetches the image manifest from the registry
and resolves each layer's blob URL.  Docker Hub redirects blob requests
to a CDN with a signed, self-authenticating URL.  The resolve phase
captures that redirect target so that Bazel's downloader can fetch it
without needing registry auth tokens.

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
| Streaming tar (`r\|gz` mode) | 72 s → 55 s (−23%) | Shipped (22be97c) | Replaced `getmembers()` O(n^2) with streaming O(n) |
| pigz parallel gzip | 55 s → 53 s (−4%) | Shipped (22be97c) | Opportunistic — detected at runtime via `shutil.which` |
| 1 MiB download chunks | 53 s → 52 s (−2%) | Shipped (22be97c) | Reduced syscall overhead (was 64 KiB) |
| Layer caching via `repository_ctx.download()` | 119 s → 25 s warm (−79%) | Shipped (PR #587) | Zero-config; uses Bazel repository cache |
| Pipeline download → extract (no temp file) | Est. −10–15% cold | Not tried | Would eliminate disk write+read per layer |
| Parallel layer downloads | N/A | Blocked | `repository_ctx.download()` is sequential in Starlark |
| zstd-compressed layers | Est. 3–5x faster decompress | Not tried | Requires registry to serve `application/vnd.oci.image.layer.v1.tar+zstd` |
| Skip resolve on cache hit | Est. −8 s | Not tried | Would cache manifest/URL mapping to avoid 21 redirect-resolution requests |

**Recommendation**: The best remaining optimization is **pipeline
download → extraction**, which eliminates writing ~1.5 GB of temp files
to disk on cold runs.  Everything else is diminishing returns or blocked
by Starlark limitations.

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

### Standalone mode

`oci_extract.py extract` still works as a standalone one-step command
(download + extract) for use outside Bazel.  The three-phase split is
only used by the `docker_pkg` repository rule.
