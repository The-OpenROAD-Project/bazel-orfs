# OpenROAD Integration

OpenROAD is the core place-and-route tool in bazel-orfs. It is built from
source via the `@openroad` module (declared with `archive_override` in the
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

Bazel honours overrides only from the root module, so a project that depends
on bazel-orfs repeats the ones bazel-orfs's own `MODULE.bazel` makes for
OpenROAD, ORFS and Yosys. The blocks below are what a downstream project
building OpenROAD from source needs, checked by building a downstream project
from a fresh clone with only Bazelisk installed.

**Pins.** `bazelisk run @bazel-orfs//:bump` keeps them current, but it runs
inside your module graph, which only resolves once OpenROAD and ORFS are
pinned to real commits. Start from the pins in bazel-orfs's own
`MODULE.bazel` at the bazel-orfs commit you choose, then let the bumper take
over. OpenROAD is an `archive_override`, not a `git_override`: an interrupted
`init_submodules` fetch can leave empty submodule directories that Bazel then
reuses, and the bumper rewrites only the `archive_override` shape.

```starlark
bazel_dep(name = "bazel-orfs")
git_override(
    module_name = "bazel-orfs",
    commit = "<bazel-orfs commit>",
    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs.git",
)

bazel_dep(name = "openroad")
archive_override(
    module_name = "openroad",
    # Copy this block verbatim from bazel-orfs's MODULE.bazel at the
    # bazel-orfs commit above, with the patch files it names: its
    # patch_cmds fetch OpenROAD's submodules and apply bazel-orfs's fixes.
    # `bazelisk run @bazel-orfs//:bump` regenerates it on every bump.
    integrity = "...",
    patch_cmds = [...],
    patch_strip = 1,
    patches = [...],
    strip_prefix = "OpenROAD-<commit>",
    urls = ["https://github.com/The-OpenROAD-Project/OpenROAD/archive/<commit>.tar.gz"],
)

bazel_dep(name = "qt-bazel")
git_override(
    module_name = "qt-bazel",
    commit = "<the qt-bazel commit bazel-orfs pins>",
    remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
)

# The slang frontend: orfs_flow synthesises with slang, and OpenROAD's syn
# compiles it. OpenROAD pins it as a submodule, which reaches no other
# root; copy this block from bazel-orfs's MODULE.bazel, with the patch it
# names. `bazelisk run @bazel-orfs//:bump` moves it with OpenROAD.
bazel_dep(name = "sv-elab", version = "<the version bazel-orfs uses>")
archive_override(
    module_name = "sv-elab",
    integrity = "...",
    patch_strip = 1,
    patches = [...],
    strip_prefix = "sv-elab-<commit>",
    urls = ["https://github.com/povik/sv-elab/archive/<commit>.tar.gz"],
)

orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.source(
    commit = "<the ORFS commit bazel-orfs pins>",
    integrity = "<its integrity>",
)
orfs.default(
    yosys_plugins = ["@sv-elab//src/yosys_plugin:slang.so"],
)
use_repo(orfs, "gnumake")
```

**Toolchain and versions.** OpenROAD builds against the BCR `llvm` module
(hermetic-llvm), registered only as a `dev_dependency`, so each root
registers it. `rules_pycross`, which OpenROAD depends on, fails on Python 3.8
unless the root configures its environments. The `single_version_override`s
pin the versions bazel-orfs builds with:

```starlark
bazel_dep(name = "llvm", version = "0.8.18")
single_version_override(module_name = "llvm", version = "0.8.18")
register_toolchains("@llvm//toolchain:all")

bazel_dep(name = "rules_pycross", version = "0.8.3")
pycross = use_extension("@rules_pycross//pycross/extensions:pycross.bzl", "pycross")
pycross.configure_environments(python_versions = ["3.13"])

bazel_dep(name = "rules_python", version = "2.3.2")
python = use_extension("@rules_python//python/extensions:python.bzl", "python")
python.toolchain(is_default = True, python_version = "3.13")

single_version_override(module_name = "sed", version = "4.9.bcr.5")
single_version_override(module_name = "gawk", version = "5.3.2.bcr.7")
single_version_override(module_name = "m4", version = "1.4.21.bcr.4")
single_version_override(module_name = "flex", version = "2.6.4.bcr.5")
single_version_override(module_name = "rules_flex", version = "0.4")
single_version_override(module_name = "rules_bison", version = "0.4.bcr.1")
single_version_override(module_name = "scip", version = "9.2.3.bcr.1")
single_version_override(module_name = "fmt", version = "12.1.0")
single_version_override(module_name = "rules_cc", version = "0.2.22")
single_version_override(module_name = "rules_cc_autoconf", version = "0.13.2")
single_version_override(module_name = "yaml-cpp", version = "0.9.0")
single_version_override(module_name = "zlib", version = "1.3.1.bcr.8")
single_version_override(module_name = "apple_support", version = "1.24.2")
```

The versions above are bazel-orfs's at the time of writing; its own
`MODULE.bazel` has the current ones, each with its reason.

**Patches.** Override patches must be files in the root module, so copy
these from bazel-orfs's `patches/` into your repository and point the
overrides at your copies. The Yosys `abc_new` fix matters to every
downstream project: without it a liberty path under
`OpenROAD-flow-scripts` reads as a `-script` option and mapping fails.

```starlark
single_version_override(
    module_name = "yosys",
    patch_strip = 1,
    patches = [
        "//patches:yosys-0001-aiger2-holes-output-order.patch",
        "//patches:yosys-0002-abc-new-script-option.patch",
    ],
)
single_version_override(
    module_name = "bison",
    patch_strip = 1,
    patches = ["//patches:0001-gnulib-wrapper-headers-use-I-not-isystem.patch"],
    version = "3.8.2.bcr.7",
)
single_version_override(
    module_name = "boost.icl",
    patch_strip = 1,
    patches = ["//patches:0001-refactor-interval-lookup-operations-icl-54.patch"],
)
```

**`.bazelrc`.** OpenROAD and Yosys build with these, as in bazel-orfs's own
`.bazelrc`:

```
build --incompatible_strict_action_env
build --features=external_include_paths
build --per_file_copt=.*external/.*@-w
build --host_per_file_copt=.*external/.*@-w
build --cxxopt=-std=c++20 --host_cxxopt=-std=c++20
build --@rules_python//python/config_settings:bootstrap_impl=script
```

### GUI Builds

The GUI, `bazelisk run <target>_<stage> gui_<stage>`, is OpenROAD's web
viewer, which every OpenROAD build has; it is served by the odb-debug
daemon (`tools/odb_debug/README.md`), and
`bazelisk run @bazel-orfs//:odb_debug -- <target>_<stage>` starts it in the
background and prints its link. The Qt GUI, `qt_<stage>`, needs the
Qt-linked build, which `--@openroad//:platform=gui` selects and only a
`//:dirty` tree started with `--qt` installs.

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

- **You must register the `llvm` (hermetic-llvm) toolchain yourself**. OpenROAD
  builds against the BCR `llvm` module (a statically linked, zero-sysroot LLVM),
  but registers it only as a `dev_dependency` — which bzlmod ignores for non-root
  modules. So `@openroad` as a dependency does not bring a toolchain with it;
  each root building OpenROAD from source must declare `bazel_dep(name = "llvm")`
  and `register_toolchains("@llvm//toolchain:all")`.

- **Dependency version conflicts**. OpenROAD may require newer versions of
  shared dependencies (`rules_cc`, `rules_shell`, etc.) than your project uses.
  bzlmod's Minimum Version Selection picks the highest declared version, which
  can cause subtle breakage if APIs changed between versions.

- **OpenROAD's remote build cache is not available to downstream users**. The
  cache at `bazel.precisioninno.com` is configured in OpenROAD's `.bazelrc` but
  is not accessible from other projects.

- **The Qt GUI requires `--@openroad//:platform=gui`**. Without this flag
  in your `.bazelrc` or on the command line, OpenROAD builds without Qt and
  `qt_<stage>` will not work; `gui_<stage>`, the web viewer, does.

## Future Upstream Improvements

These changes in OpenROAD would improve the experience for downstream users:

- **Hermetic toolchain doesn't propagate to consumers** — OpenROAD registers
  the `llvm` (hermetic-llvm) toolchain only as a `dev_dependency`, so every
  downstream root that builds OpenROAD from source has to re-declare
  `bazel_dep(name = "llvm")` + `register_toolchains("@llvm//toolchain:all")`.
  A propagating registration (or a documented shared macro) would remove that
  duplication.

- **qt-bazel in BCR** — would eliminate the `git_override` burden; currently
  every consumer must re-declare it.

- **Make more dependencies `dev_dependency`** — many boost
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

### Why the bump looks slow

A bump often appears to take minutes before it prints anything. Almost
none of that is the bumper. `MODULE.bazel` declares OpenROAD as
`bazel_dep` + `archive_override`, and bzlmod cannot resolve the module
graph without reading every dependency's `MODULE.bazel`. A registry dep
serves that file on its own — a few KB out of BCR. An `archive_override`
has no way to hand Bazel just the module file, so to read those ~100
lines Bazel downloads and unpacks the entire OpenROAD tarball and runs
its `patch_cmds`, which themselves fetch three submodule archives. It
happens in "Computing main repo mapping", before a single target is
analyzed, and it is measured in minutes:

```
$ time bazelisk build --nobuild //:bump
Computing main repo mapping:
INFO: Repo openroad+ defined by rule http_archive ...
real  6m56s
```

Every Bazel command in the workspace pays that once per pin —
`//:fix_lint` and `bazelisk query` included. The bumper looks like the
culprit only because it is the command that *creates* an unfetched pin: it
rewrites the OpenROAD and ORFS commits and exits, so whatever runs next,
very often the next `//:bump`, is the first to meet a SHA nothing has
downloaded. The download is real work a build needs; the bumper needs
none of it.

Nothing about this is fixable inside the bumper. The fix would be serving
openroad's module file from a registry instead of an override, and
`source.json` has no `patch_cmds`, so the submodule vendoring would have
to become patches regenerated on every bump. That is a bigger,
churn-prone change than the cost it saves, and it would only help this
root — a downstream root writes its own
`archive_override` from the template in the README.

### Shapes the bumper recognizes

`bump.py` is a thin loader: it downloads the newest `bump_impl.py` from
`main` on every run, so the implementation is never stale. The only thing
that can be out of date is *your* `MODULE.bazel` — the override shapes the
bumper has to recognize in order to rewrite them. Carrying migration paths
for every shape bazel-orfs has ever emitted made the bumper slower, larger
and riskier than the thing it was migrating, so those paths are deleted
rather than maintained.

That leaves one rule, and no dates: **the bumper rewrites what it
recognizes, and stops when it does not.** Each rewrite is guarded by a
precondition naming the block it needs, so a `git_override(module_name =
"orfs")` where an `archive_override` is expected fails with

```
Expected archive_override(module_name = "orfs") in MODULE.bazel but found
no match
```

The refusal is safe as well as loud: `MODULE.bazel` is read once and
written once, at the end, so a refused bump writes nothing and the file is
left byte-identical. There is nothing to half-rewrite and nothing to
recover.

Two ways forward when a shape is refused:

1. **Re-seed** — copy the current blocks from
   [Root MODULE.bazel requirements](#root-modulebazel-requirements),
   re-apply your local edits, re-run `//:bump`.
2. **`--ignore`** — downgrade the refusal to a warning and take the parts
   the bumper does recognize. The unrecognized block is left exactly as it
   was, for you to fix by hand.

Compatibility code in `bump_impl.py` is temporary by the same logic: a
migration branch for a shape bazel-orfs no longer emits is deleted, not
maintained. There is one today, for an upstream shape rather than yours:
OpenROAD replaced its `third-party/slang-elab` submodule with
`third-party/sv-elab`, and ORFS's OpenROAD pin may still be on either side
of that, so the bumper vendors slang-elab only while the commit has it
(`OPENROAD_TRANSITIONAL_SUBMODULES`). It goes once ORFS's `tools/OpenROAD`
is past the change.

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
