# OpenROAD Integration

OpenROAD is the core place-and-route tool in bazel-orfs. By default, it uses
the pre-built binary from the ORFS image (`@docker_orfs//:openroad`).
This is the fastest option and requires no compilation.

For users who need to test a newer OpenROAD before the ORFS image is updated,
bazel-orfs supports building OpenROAD from source via `bazel_dep` +
`git_override`, or using a locally installed binary via a PATH wrapper.

## Default Configuration

The default uses the ORFS image binary, configured in `MODULE.bazel`:

```starlark
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default(
    image = "docker.io/openroad/orfs:...",
    sha256 = "...",
    # openroad defaults to @docker_orfs//:openroad (from ORFS image)
)
```

No additional setup is needed for the default configuration.

## Building OpenROAD from Git Source

OpenROAD has a native Bazel build (`cc_binary` at `//:openroad`). The easiest
way to get started is to run `bazelisk run @bazel-orfs//:bump` — it injects
commented-out boilerplate for building OpenROAD from source into your
`MODULE.bazel`. Uncomment it to enable.

Alternatively, add these to your `MODULE.bazel` manually:

```starlark
bazel_dep(name = "openroad")
git_override(
    module_name = "openroad",
    commit = "<commit-sha>",
    init_submodules = True,
    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",
)

# Required: qt-bazel is not in BCR and must be overridden in the root module.
# OpenROAD's own git_override is ignored because only root module overrides apply.
bazel_dep(name = "qt-bazel")
git_override(
    module_name = "qt-bazel",
    commit = "df022f4ebaa4130713692fffd2f519d49e9d0b97",
    remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
)

# Required: OpenROAD needs the LLVM toolchain for compilation.
bazel_dep(name = "toolchains_llvm", version = "1.5.0")
```

Then override the openroad binary globally:

```starlark
orfs.default(
    image = "docker.io/openroad/orfs:...",
    sha256 = "...",
    openroad = "@openroad//:openroad",
)
```

### GUI Builds

The ORFS image ships OpenROAD with GUI support. bazel-orfs builds OpenROAD
from source with GUI enabled by default (`--@openroad//:platform=gui` in
`.bazelrc`) to match the Docker image.

To disable GUI (CLI-only mode), override in `user.bazelrc`:

```
build --@openroad//:platform=cli
```

## Per-Target Override

The `openroad` argument can be passed to `orfs_flow()` to override it for a
specific design, similar to how `klayout` works on `orfs_gds`:

```starlark
load("@bazel-orfs//:openroad.bzl", "orfs_flow")

orfs_flow(
    name = "my_design",
    openroad = "@openroad//:openroad",
    verilog_files = ["my_design.v"],
    # ...
)
```

When not set, it defaults to the global openroad configured in `orfs.default()`.

## Using a Locally Installed OpenROAD

To use an OpenROAD binary already installed on your system (e.g. one you built
locally with GUI support):

```starlark
orfs.default(
    image = "docker.io/openroad/orfs:...",
    sha256 = "...",
    openroad = "@bazel-orfs//:openroad",
)
```

The `@bazel-orfs//:openroad` wrapper executes whichever `openroad` binary is
found on the system `PATH`. For hermetic builds, prefer the ORFS image default
or building from source via `git_override`.

## Mock OpenROAD for Testing

For CI and development, a mock openroad binary is provided that exits
successfully without running real place-and-route. This is useful for testing
the override mechanism without the cost of a real OpenROAD build.

The mock binaries are regular packages within bazel-orfs, so downstream
consumers reference them as `@bazel-orfs//mock/openroad/src/bin:openroad`.

To use the mock per-target in tests:

```starlark
orfs_flow(
    name = "my_design_mock_openroad",
    openroad = "//mock/openroad/src/bin:openroad",
    # ...
)
```

## Gotchas

Things that can surprise you when building OpenROAD from source:

- **qt-bazel `git_override` must be in your root `MODULE.bazel`**. bzlmod
  silently ignores `git_override` from non-root modules. If you forget this,
  you'll get a "module not found" error for qt-bazel.

- **First build is slow**. OpenROAD pulls in ~30 boost modules, or-tools,
  tcmalloc, Qt, eigen, swig, and more. Expect 30-60+ minutes for a cold build.
  Subsequent builds are incremental.

- **`toolchains_llvm` is pulled in**. OpenROAD pins LLVM 20.1.8 as its C++
  compiler toolchain. This may conflict with your local compiler setup or other
  toolchain registrations. Non-root toolchain registrations have lower priority,
  so it won't override your root module's toolchain if you have one.

- **Dependency version conflicts**. OpenROAD may require newer versions of
  shared dependencies (`rules_cc`, `rules_shell`, etc.) than your project uses.
  bzlmod's Minimum Version Selection picks the highest declared version, which
  can cause subtle breakage if APIs changed between versions.

- **OpenROAD's remote build cache is not available to downstream users**. The
  cache at `bazel.precisioninno.com` is configured in OpenROAD's `.bazelrc` but
  is not accessible from other projects.

- **GUI requires `--@openroad//:platform=gui`**. Without this flag in your
  `.bazelrc` or on the command line, OpenROAD builds in CLI-only mode and
  `bazel run` targets that open the GUI will not work.

## Current Workarounds

These hacks are needed to use OpenROAD as a bazel_dep. Each will be removed
as the corresponding upstream fix lands:

| Hack | Why | Remove when |
|------|-----|-------------|
| `qt-bazel` git_override in root | bzlmod ignores git_override from non-root modules | qt-bazel is published to BCR |
| llvm extension + register_toolchains in root MODULE.bazel | `toolchains_llvm` extension enforces root-module-only usage; OpenROAD now marks it dev_dependency so the root module must provide it | OpenROAD publishes to BCR with toolchain config |

## Future Upstream Improvements

These changes in OpenROAD would improve the experience for downstream users:

- **`toolchains_llvm` root-only workaround** — OpenROAD should make the llvm
  extension usage conditional on being the root module, or move to a different
  toolchain configuration pattern that works from non-root modules. This would
  eliminate the patch and root-module llvm configuration hack.

- **qt-bazel in BCR** — would eliminate the `git_override` burden; currently
  every consumer must re-declare it.

- **Make more dependencies `dev_dependency`** — `toolchains_llvm`, many boost
  modules, `or-tools`, `tcmalloc`, `eigen`, `swig` etc. are pulled into every
  downstream project's dependency graph. Making non-essential-for-API deps into
  `dev_dependency` would reduce the transitive dependency burden.

- **Reduce version pinning conflicts** — OpenROAD pins specific versions of
  `rules_cc`, `rules_shell`, etc. that may conflict with downstream projects.

- **Remote cache availability** — making the build cache accessible to
  downstream users or publishing pre-built artifacts would dramatically reduce
  first-build time.

## Bumping Versions with `//:bump`

`bazelisk run @bazel-orfs//:bump` (or `bazelisk run //:bump` from within
bazel-orfs) is a single command that updates all version pins. It detects
which project it's running in and does the right thing:

| What it updates | bazel-orfs | OpenROAD | User project |
|----------------|-----------|---------|-------------|
| ORFS image + sha256 | yes | yes | yes |
| bazel-orfs git commit | — (is self) | yes | yes |
| OpenROAD git commit | yes | — (is self) | yes (if present) |
| Inject commented-out OR-from-source | — (has it) | — (is OR) | yes |

In a downstream project, after running bump, you'll see commented-out
`bazel_dep` / `git_override` blocks for OpenROAD in your `MODULE.bazel`.
Uncomment them to build OpenROAD from source. The OpenROAD commit is
already filled in with the latest value.

Detection works by checking `module(name = ...)` in `MODULE.bazel`:
`bazel-orfs` and `openroad` are recognized; everything else is treated
as a downstream project.

## Testing

### CI (fast, uses mock)

```sh
# Test the openroad override mechanism (~2.5s, mock openroad)
bazelisk build //test:lb_32x128_mock_openroad_floorplan
```

### Local: test latest OpenROAD GUI from source

After bumping OpenROAD to the latest commit:

```sh
# 1. Bump OpenROAD (and ORFS image) to latest versions
bazelisk run //:bump

# 2. Open synthesis results in the source-built OpenROAD GUI
#    First build is slow (~30-60min), subsequent builds are incremental.
bazelisk run //test:lb_32x128_openroad_gui_synth
```

This builds OpenROAD from git source with GUI enabled (via
`--@openroad//:platform=gui` in `.bazelrc`), runs synthesis, and opens
the results in the OpenROAD GUI. The target is tagged `manual` so it
won't run in CI.

### Other useful commands

```sh
# Build just the OpenROAD binary from source
bazelisk build @openroad//:openroad

# Run a flow stage with source-built OpenROAD (no GUI)
bazelisk build //test:lb_32x128_openroad_gui_floorplan
```
