# OpenROAD Integration

OpenROAD is the core place-and-route tool in bazel-orfs. It is built from
source via the `@openroad` module (declared with `git_override` in the
root `MODULE.bazel`). OpenROAD and OpenSTA come from the same source
tree.

## Default Configuration

The default `orfs.default()` points at `@openroad//:openroad` and
`@openroad//src/sta:opensta` — no explicit override is needed:

```starlark
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default()
```

## Root MODULE.bazel requirements

bzlmod only honors `git_override` from the root module, so every root
module that depends on bazel-orfs must declare the OpenROAD and qt-bazel
overrides. `bazelisk run @bazel-orfs//:bump` injects these automatically
alongside the bazel-orfs pin:

```starlark
bazel_dep(name = "openroad")
git_override(
    module_name = "openroad",
    commit = "<commit-sha>",
    init_submodules = True,
    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",
)

bazel_dep(name = "qt-bazel")
git_override(
    module_name = "qt-bazel",
    commit = "<commit-sha>",
    remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
)

bazel_dep(name = "toolchains_llvm", version = "1.5.0")
```

### GUI Builds

bazel-orfs enables OpenROAD's GUI by default via `--@openroad//:platform=gui`
in `.bazelrc`. To disable it (CLI-only mode), override in `user.bazelrc`:

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

To use an OpenROAD binary already installed on your system (e.g. one you
built locally):

```starlark
orfs.default(
    openroad = "@bazel-orfs//:openroad",
)
```

The `@bazel-orfs//:openroad` wrapper execs whichever `openroad` binary is
found on the system `PATH`. For hermetic builds, prefer the source-built
default.

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

## Future Upstream Improvements

These changes in OpenROAD would improve the experience for downstream users:

- **`toolchains_llvm` root-only workaround** — OpenROAD should make the llvm
  extension usage conditional on being the root module, or move to a different
  toolchain configuration pattern that works from non-root modules.

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

| What it updates       | bazel-orfs   | OpenROAD  | User project    |
|-----------------------|--------------|-----------|-----------------|
| bazel-orfs git commit | — (is self)  | yes       | yes             |
| OpenROAD git commit   | yes          | — (is self) | yes (if present) |
| ORFS git commit       | yes          | —         | —               |
| qt-bazel git commit   | yes          | —         | yes (if present) |
| Non-BCR deps injected | —            | —         | yes (on first bump) |

Detection works by checking `module(name = ...)` in `MODULE.bazel`:
`bazel-orfs` and `openroad` are recognized; everything else is treated
as a downstream project.

## Testing

### CI (fast, uses mock)

```sh
# Test the openroad override mechanism (~2.5s, mock openroad)
bazelisk build //test:lb_32x128_mock_openroad_floorplan
```

### Local: test the source-built OpenROAD GUI

```sh
# 1. Bump OpenROAD to the latest versions
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
