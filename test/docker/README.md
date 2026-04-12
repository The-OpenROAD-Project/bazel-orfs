# Docker-based OpenROAD Test

This workspace demonstrates using the OpenROAD binary from the ORFS
Docker image instead of building OpenROAD from source.

## Why

Building OpenROAD from source requires `openroad`, `qt-bazel`, and
`toolchains_llvm` Bazel dependencies — a heavyweight setup that takes
significant compile time. The Docker image ships a pre-built OpenROAD
binary (with GUI support) that can be used directly.

## Configuration

The key line in `MODULE.bazel`:

```python
orfs.default(
    openroad = "@bazel-orfs//:openroad-latest",
    opensta = "@bazel-orfs//:opensta-latest",
)
```

This replaces the default source-built `@openroad//:openroad` with
the Docker-extracted binary. No `bazel_dep(name = "openroad")`,
`qt-bazel`, or `toolchains_llvm` is needed.

The Docker image is only downloaded when a target that uses OpenROAD
is actually built — the multi-GB download is lazy.

## Usage

```bash
cd test/docker

# Run synthesis
bazelisk build //:counter_synth

# Open the OpenROAD GUI (Docker OpenROAD has GUI built in)
bazelisk run //:counter_gui_synth
```

## Contrast: source-built OpenROAD with GUI

When building OpenROAD from source (the default in bazel-orfs), GUI
support requires the `--@openroad//:platform=gui` build flag:

```bash
# In .bazelrc:
build --@openroad//:platform=gui

# Or use the pre-defined config:
bazelisk build --config=openroad-gui @openroad//:openroad
```

The Docker-based approach (`@bazel-orfs//:openroad-latest`) does not
need this flag — the Docker image's OpenROAD binary already includes
GUI support.

## Updating the Docker image

Run `bazelisk run @bazel-orfs//:bump` to update to the latest ORFS
Docker image tag. This updates the `LATEST_ORFS_IMAGE` and
`LATEST_ORFS_SHA256` constants in `extension.bzl`.
