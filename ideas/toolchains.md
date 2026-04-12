# Caching and Pinning: Toolchains and Packages

## Context

bazel-orfs relies on two large foundational tools -- yosys and
OpenROAD -- plus ORFS flow scripts and PDK files. Getting these
tools to users efficiently requires two complementary strategies:

1. **Caching** -- Bazel's transparent build cache. When all inputs
   are unchanged, skip the rebuild automatically. This is correct
   by construction and works well for application code that changes
   frequently.

2. **Pinning** -- An explicit, intentional declaration: "use this
   exact binary (identified by sha256) regardless of whether source
   inputs have changed." Pinning is deliberate non-invalidation,
   made with the understanding that in theory the tool should be
   rebuilt, but in practice the rebuild is not worth the cost.

Neither is right or wrong -- they serve different needs. For
application RTL and flow scripts, caching is exactly what you want:
change a Verilog file, re-synthesize automatically. For foundational
tools that change rarely and cost dearly to rebuild (yosys: 10-20
min, OpenROAD: 30-60+ min), pinning lets the user decide when an
upgrade is worth the time. Both belong in the same build system.

Today bazel-orfs has good caching but no pinning story. A one-line
change in an OpenROAD header that is irrelevant to the user's flow
correctly invalidates the cache and triggers a full rebuild. The
user cannot express "I know the input changed, but I intentionally
want to keep using the binary I have validated." A cache cannot and
should not capture this intention -- that is what pinning is for.

3. **Patching** -- Users hit bugs in upstream tools. Without
   pinning, a broken upstream means an urgent fire: the build is
   broken *now*, and the only options are to fix upstream (slow,
   someone else's repo) or carry a source-build patch stack that
   every developer must rebuild locally. Pinning changes the
   equation: a user applies a patch, builds once, pins the
   resulting binary by sha256, and shares it with their team.
   The rest of the team downloads the pinned binary in seconds
   without rebuilding. "Broken upstream" stops being an emergency
   and becomes a tracked issue to resolve at the right time.
   Pinning makes patching practical, and patching makes pinning
   indispensable -- together they turn broken into non-urgent.

   Crucially, patches carried this way can **build up and stabilize**
   before being pitched upstream. A patch that fixes a crash in a
   user's flow today may need reworking to meet upstream standards,
   or may interact with other patches in ways that only become clear
   over time. By carrying patches locally behind a pin, users can
   let the patch stack mature -- merge related fixes, refine the
   approach, confirm the fix holds across designs -- and only then
   propose a well-tested PR upstream. This reduces stress and churn
   for everyone: upstream maintainers review fewer, better patches,
   and downstream users are not pressured to rush half-baked fixes
   into someone else's repository just to unblock their builds.

Additionally:

- **Build time**: yosys takes 10-20 minutes from source, OpenROAD
  takes 30-60+ minutes. Both require a C++20 compiler, cmake, and
  platform-specific development headers.

- **Clone size**: ORFS is a 1.1 GB git checkout. bazel-orfs only
  needs ~830 KB of scripts/makefiles plus PDK platform files, but
  `git_override` clones the entire repo including 265 MB of unused
  design examples.

The proper long-term fix is for yosys and OpenROAD to publish
first-class Bazel modules on the Bazel Central Registry (BCR), with
pre-built binaries and proper toolchain definitions. That is not
something we control, and it will take time.

These toolchains and packages are **pain-relief for bazel-orfs** --
stop-gap solutions we own and ship today, hosted as GitHub Release
assets on the `The-OpenROAD-Project/bazel-orfs` repository. When
upstream tools eventually appear on the BCR, we retire these
stop-gaps. Until then, they give users both fast caching for their
own code and intentional pinning for their tools.

### Expected savings

The pain hits two audiences differently:

**Students and users on modest hardware** -- A student on an older
laptop or hand-me-down workstation (2-4 cores, 8 GB RAM) can wait
2-3+ hours for a clean build of yosys + OpenROAD. This is the worst
case and the most important to fix: it makes bazel-orfs unusable as
a teaching tool or for casual exploration. Pre-built binaries turn
this into a download that completes in under a minute.

**CI (GitHub Actions)** -- A 4-core GitHub runner takes over an hour
for the same build. See
[run #24082757239](https://github.com/The-OpenROAD-Project/bazel-orfs/actions/runs/24082757239/job/70247759190)
for a representative example. CI builds that compile from source
regularly approach or exceed the 6-hour job timeout, and the ORFS
git clone adds further delay. Pre-built packages make CI fast and
predictable.

| Component       | Today (source build)         | With pre-built packages          |
|-----------------|------------------------------|----------------------------------|
| **Yosys**       | 15 min (CI) / 30+ min (laptop) compile, ~200 MB src | ~50 MB download, seconds |
| **OpenROAD**    | 45 min (CI) / 2+ hrs (laptop) compile, ~2 GB src+deps | ~150 MB download, seconds |
| **ORFS clone**  | ~1.1 GB git clone            | ~1 MB tarball (scripts only)     |
| **All PDKs**    | included in ORFS clone (778 MB) | per-PDK download (e.g. 20 MB for sky130hd) |
| **Total**       | **1+ hr (CI) / 3+ hrs (laptop), ~3.3 GB** | **seconds, ~220 MB** (one PDK) |

For a student who only needs sky130hd, the experience goes from
"wait 3 hours before you can run your first synthesis" to "download
220 MB and start immediately".

## What changes

Today tools are wired through `global_config.bzl` string labels
and overridable rule attributes (`CONFIG_YOSYS`, `CONFIG_OPENROAD`,
etc.). There is no `toolchain_type`, no platform resolution, and no
clean way for downstream users to swap in their own builds. ORFS is
pulled as a full git clone via `git_override`, downloading ~1.1 GB
when only ~830 KB of scripts plus PDK files are needed.

The plan:

1. Define a proper Bazel `toolchain_type` for yosys and OpenROAD.
2. Ship pre-built binaries as GitHub Release assets on `bazel-orfs`.
3. Package ORFS scripts/makefiles and each PDK as separate
   downloadable tarballs, eliminating the full ORFS git clone.
4. Default to downloading pre-built binaries and packages; keep
   source/git builds as opt-in.
5. Retire `global_config` entries once migration is complete.

---

## Yosys toolchain

### Current state

`bazel-orfs/yosys/` downloads yosys, ABC, cxxopts, yosys-slang, slang,
fmt, TCL, and flex sources, then builds everything via a genrule that
shells out to `make install` and `cmake`. The resulting binaries
(`yosys`, `yosys-abc`) and share directory (techmap, plugins including
`slang.so`) are consumed through `CONFIG_YOSYS` / `CONFIG_YOSYS_ABC` /
`CONFIG_YOSYS_SHARE` in `global_config.bzl`.

### Proposed structure

Keep the existing `bazel-orfs/yosys/` submodule but reorganise it:

```
yosys/
  MODULE.bazel           # module "bazel-orfs-yosys"
  BUILD.bazel            # toolchain_type + default toolchain registrations
  extension.bzl          # module extension: register prebuilt or source toolchains
  toolchain.bzl          # toolchain_type, YosysInfo provider, toolchain rule
  prebuilt.bzl           # repository rule: download + extract prebuilt binaries
  source.bzl             # repository rule: download sources + genrule build (current logic)
  repo.BUILD.bazel       # BUILD for source-built repository (current file)
  prebuilt.BUILD.bazel   # BUILD for prebuilt repository
  rules.bzl              # extract_share (unchanged)
  private/
    versions.bzl         # default commit SHAs and prebuilt URLs/sha256s
```

### Provider

```python
YosysInfo = provider(
    doc = "Information about a Yosys toolchain.",
    fields = {
        "yosys": "File: the yosys binary",
        "abc": "File: the yosys-abc binary",
        "share": "File: the yosys share directory (tree artifact)",
    },
)
```

### Toolchain type and rule

```python
# yosys/toolchain.bzl

YOSYS_TOOLCHAIN_TYPE = "@bazel-orfs-yosys//:toolchain_type"

def _yosys_toolchain_impl(ctx):
    return [platform_common.ToolchainInfo(
        yosys_info = YosysInfo(
            yosys = ctx.executable.yosys,
            abc = ctx.executable.abc,
            share = ctx.file.share,
        ),
    )]

yosys_toolchain = rule(
    implementation = _yosys_toolchain_impl,
    attrs = {
        "yosys": attr.label(mandatory = True, executable = True, cfg = "exec"),
        "abc": attr.label(mandatory = True, executable = True, cfg = "exec"),
        "share": attr.label(mandatory = True, allow_single_file = True),
    },
)
```

```python
# yosys/BUILD.bazel

toolchain_type(
    name = "toolchain_type",
    visibility = ["//visibility:public"],
)
```

### Module extension

```python
# yosys/extension.bzl (rewritten)

yosys = module_extension(...)

# Tags:
#   yosys.prebuilt(version = "0.48", ...)  -- default
#   yosys.source(yosys_commit = "...", abc_commit = "...", ...)  -- opt-in
```

The extension creates a `@yosys` repository (prebuilt or source) and
calls `register_toolchains("@yosys//:toolchain")`.

### Consuming the toolchain in rules

In `private/attrs.bzl` and `private/environment.bzl`, replace the
current label-based config with toolchain resolution:

```python
# In rule implementation:
yosys_info = ctx.toolchains[YOSYS_TOOLCHAIN_TYPE].yosys_info
yosys_exe = yosys_info.yosys
abc_exe = yosys_info.abc
share_dir = yosys_info.share
```

Rules declare the toolchain dependency:

```python
orfs_synth = rule(
    ...
    toolchains = [YOSYS_TOOLCHAIN_TYPE],
)
```

This eliminates `CONFIG_YOSYS`, `CONFIG_YOSYS_ABC`, and
`CONFIG_YOSYS_SHARE` from `global_config.bzl`.

---

## OpenROAD toolchain

### Current state

OpenROAD is pulled via `git_override` in `MODULE.bazel`, pointing at a
specific commit of `The-OpenROAD-Project/OpenROAD.git`. It builds from
source as a full C++20 project with LLVM toolchain, boost, or-tools,
tcmalloc, Eigen, SWIG, and many other dependencies. Build time is
30-60+ minutes cold.

The binaries (`openroad`, `opensta`) are wired through `CONFIG_OPENROAD`
and `CONFIG_OPENSTA` in `global_config.bzl`, with per-rule attribute
overrides. Runtime dependencies (TCL, Ruby, Qt, OpenGL libraries) come
from a Docker image (`@docker_orfs`) or are stubbed out.

A visibility patch (`openroad-visibility.patch`) is applied to expose
internal libraries needed by bazel-orfs.

### Proposed structure

Add a `bazel-orfs/openroad/` submodule (mirrors the yosys pattern):

```
openroad/
  MODULE.bazel              # module "bazel-orfs-openroad"
  BUILD.bazel               # toolchain_type + default toolchain registrations
  extension.bzl             # module extension: register prebuilt or source toolchains
  toolchain.bzl             # toolchain_type, OpenroadInfo provider, toolchain rule
  prebuilt.bzl              # repository rule: download + extract prebuilt binaries
  prebuilt.BUILD.bazel      # BUILD for prebuilt repository
  private/
    versions.bzl            # default commit SHAs and prebuilt URLs/sha256s
```

Source builds continue to use `git_override` on the upstream OpenROAD
repository (no need to duplicate their Bazel build). The prebuilt path
is the new addition.

### Provider

```python
OpenroadInfo = provider(
    doc = "Information about an OpenROAD toolchain.",
    fields = {
        "openroad": "File: the openroad binary",
        "opensta": "File: the opensta binary",
        "tcl_lib": "File: TCL shared library (runtime dependency)",
    },
)
```

### Toolchain type and rule

```python
# openroad/toolchain.bzl

OPENROAD_TOOLCHAIN_TYPE = "@bazel-orfs-openroad//:toolchain_type"

def _openroad_toolchain_impl(ctx):
    return [platform_common.ToolchainInfo(
        openroad_info = OpenroadInfo(
            openroad = ctx.executable.openroad,
            opensta = ctx.executable.opensta,
            tcl_lib = ctx.file.tcl_lib,
        ),
    )]

openroad_toolchain = rule(
    implementation = _openroad_toolchain_impl,
    attrs = {
        "openroad": attr.label(mandatory = True, executable = True, cfg = "exec"),
        "opensta": attr.label(mandatory = True, executable = True, cfg = "exec"),
        "tcl_lib": attr.label(mandatory = False, allow_single_file = True),
    },
)
```

### Consuming the toolchain in rules

```python
# In rule implementation:
openroad_info = ctx.toolchains[OPENROAD_TOOLCHAIN_TYPE].openroad_info
openroad_exe = openroad_info.openroad
opensta_exe = openroad_info.opensta
```

Rules declare:

```python
orfs_flow = rule(
    ...
    toolchains = [YOSYS_TOOLCHAIN_TYPE, OPENROAD_TOOLCHAIN_TYPE],
)
```

This eliminates `CONFIG_OPENROAD` and `CONFIG_OPENSTA` from
`global_config.bzl`.

### OpenROAD-specific considerations

**GUI is required on Ubuntu prebuilts**: Pre-built OpenROAD binaries
(linux-x86_64) are built with GUI enabled (`-DBUILD_GUI=ON`). The GUI
is a core part of the OpenROAD workflow -- users need it for design
visualization, debugging placement/routing, and interactive
exploration. This means prebuilt tarballs bundle Qt and expect OpenGL
from the host system (mesa/GPU driver).

**GUI-less fallback on other platforms**: Users on non-Ubuntu platforms
build from source. These source builds default to GUI-less
(`-DBUILD_GUI=OFF`) since Qt cross-compilation is non-trivial and
not every platform has Qt packages readily available. This still gives
a fully functional OpenROAD for batch RTL-to-GDS flows -- only the
interactive GUI is missing.

**Runtime libraries**: With GUI enabled, OpenROAD dynamically links
TCL, Ruby, Qt, and OpenGL. Pre-built tarballs bundle TCL, Ruby, and
Qt libraries in a `lib/` directory resolved via `RPATH`. OpenGL is
the sole host dependency (mesa/GPU driver).

**OpenSTA**: Shipped as a separate binary (`opensta`) built from
`src/sta/` in the OpenROAD tree. Pre-built tarballs include both
binaries.

**Visibility patch**: No longer needed for prebuilt binaries (we ship
the final executables, not Bazel library targets). The patch remains
relevant only for the source-build path.

---

## ORFS scripts and makefiles package

### Current state

ORFS is pulled via `git_override` in `MODULE.bazel`, cloning the
entire `OpenROAD-flow-scripts` repository (~1.1 GB). Of that,
bazel-orfs actually uses:

- `flow/Makefile` (36 KB) -- the main ORFS makefile
- `flow/scripts/` (444 KB) -- Python and TCL scripts
- `flow/util/` (352 KB) -- utility scripts
- `flow/scripts/variables.yaml` -- variable metadata

That is ~830 KB of useful content out of a 1.1 GB clone. The rest
(265 MB of design examples, 4.3 MB of tutorials, docs, tools) is
never used by bazel-orfs consumers.

### Proposed package

Package the ORFS scripts and makefiles as a tarball hosted on
bazel-orfs GitHub Releases:

```
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/orfs/v<commit-short>/orfs-flow-<commit-short>.tar.gz
```

The tarball contains only what bazel-orfs needs:

```
orfs-flow-<commit-short>/
  Makefile
  Makefile.yosys
  scripts/            # Python + TCL flow scripts
  util/               # utility scripts
  scripts/variables.yaml
```

A repository rule downloads and extracts this instead of cloning the
full ORFS repo. The `orfs_pdk` rule definitions (currently injected
via patch) move into bazel-orfs itself since they are bazel-orfs's
own BUILD logic, not upstream ORFS content.

### What this eliminates

- The 1.1 GB ORFS git clone (replaced by ~1 MB tarball download).
- The `git_override` for ORFS in `MODULE.bazel`.
- The patch stack against ORFS (`patches/0001-...`, `patches/0002-...`,
  `patches/0035-...`) -- the patches exist to inject Bazel build logic
  into ORFS; with a standalone package, the BUILD file ships directly.

---

## PDK packages

### Current state

PDK platform files live inside the ORFS repo under
`flow/platforms/<pdk>/`. They are pulled as part of the full ORFS
git clone. All 6 PDKs (~778 MB total) are always downloaded even if
a user only needs one:

| PDK        | Size  |
|------------|-------|
| asap7      | 222 MB|
| sky130ram  | 214 MB|
| sky130hs   | 110 MB|
| gf180      | 108 MB|
| ihp-sg13g2 | 97 MB |
| sky130hd   | 20 MB |
| nangate45  | 10 MB |

### Proposed packages

Each PDK is packaged as a separate tarball on bazel-orfs GitHub
Releases. Users download only the PDK(s) they need:

```
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/pdk/asap7/<commit-short>/asap7-<commit-short>.tar.gz
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/pdk/sky130hd/<commit-short>/sky130hd-<commit-short>.tar.gz
# ... etc.
```

Each tarball contains the platform directory contents plus a
`BUILD.bazel` with the `orfs_pdk` target:

```
asap7-<commit-short>/
  BUILD.bazel          # orfs_pdk(name = "asap7", ...)
  config.mk
  lib/                 # .lib, .lib.gz files
  lef/                 # LEF files
  ...                  # other PDK-specific files
```

A repository rule downloads the PDK tarball:

```python
# pdk/repository.bzl

def _orfs_pdk_impl(repository_ctx):
    repository_ctx.download_and_extract(
        url = repository_ctx.attr.url,
        sha256 = repository_ctx.attr.sha256,
    )
    # BUILD.bazel is included in the tarball

orfs_pdk_repo = repository_rule(
    implementation = _orfs_pdk_impl,
    attrs = {
        "url": attr.string(mandatory = True),
        "sha256": attr.string(default = ""),
    },
)
```

### What this eliminates

- Downloading all 778 MB of PDKs when only one is needed. A typical
  user working with `sky130hd` downloads 20 MB instead of 778 MB.
- PDK files are no longer coupled to the ORFS git history -- they
  are versioned independently as release assets.

### PDK selection in the module extension

The module extension gains per-PDK configuration:

```python
# In consumer's MODULE.bazel:
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.default(
    pdk = "asap7",  # downloads only asap7 PDK package
)
```

Or for multiple PDKs:

```python
orfs.default()
orfs.pdk(name = "asap7")
orfs.pdk(name = "sky130hd")
```

---

## Hosting: GitHub Releases on `bazel-orfs`

All pre-built binaries and packages are hosted as GitHub Release
assets on `The-OpenROAD-Project/bazel-orfs` -- the repo we already
have. Tags use namespaced prefixes to avoid collisions:

```
# Yosys (linux-x86_64 only; other platforms build from source)
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/yosys/v0.48/yosys-0.48-linux-x86_64.tar.gz

# OpenROAD (linux-x86_64 only, GUI enabled; other platforms build from source)
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/openroad/v2.0-19336/openroad-2.0-19336-linux-x86_64.tar.gz

# ORFS flow scripts and makefiles
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/orfs/v<commit-short>/orfs-flow-<commit-short>.tar.gz

# PDKs (one per PDK)
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/pdk/asap7/<commit-short>/asap7-<commit-short>.tar.gz
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/pdk/sky130hd/<commit-short>/sky130hd-<commit-short>.tar.gz
https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/pdk/nangate45/<commit-short>/nangate45-<commit-short>.tar.gz
# ... etc.
```

Why this works well:
- No new repository or external hosting needed.
- `sha256` pinned in `private/versions.bzl` next to source commit SHAs.
- Single place to update when bumping: change commits, CI rebuilds, new
  release tag, update sha256s.
- GitHub releases are immutable and CDN-backed.
- Works with `repository_ctx.download_and_extract()` directly.
- 2 GB per-release asset limit is not a concern (yosys ~50 MB,
  OpenROAD ~150 MB, ORFS flow ~1 MB, largest PDK ~222 MB).

### Alternatives considered

**Dedicated repositories** -- Separate GitHub repos for yosys and
OpenROAD releases. Rejected: requires creating repos we don't have and
adds coordination overhead.

**Bazel Central Registry (BCR)** -- The right long-term home. Not
viable today: neither tool is a stable standalone Bazel module, BCR
publication has significant ceremony, and we need control over what
plugins are included (yosys-slang) and how binaries are linked. When
these tools eventually appear on the BCR with pre-built binaries, we
retire our stop-gap toolchains and point users at the upstream modules.

**YosysHQ `oss-cad-suite` nightly releases** -- Pre-built yosys
bundles at `github.com/YosysHQ/oss-cad-suite-build/releases`. Rejected:
no yosys-slang plugin, unstable nightly tags, bloated ~400 MB bundles.
Does not cover OpenROAD at all.

**ORFS Docker image** -- The `@docker_orfs` approach was the original
way to provide pre-built binaries, extracting them from the ORFS Docker
image. It has been retired in favor of building from source, but
vestiges remain throughout the codebase: `stub.bzl` stubs out the
Docker targets, `config.bzl` still defaults some labels to
`@docker_orfs`, and `private/attrs.bzl` has private fallback attributes
pointing at it. These should be pruned as part of Phase 3.

### Bump and release workflow

Updating a tool version is a three-step process: bump to latest
upstream, build to verify, then release. Two Bazel targets automate
this:

- `bazelisk run //:bump-yosys` or `bazelisk run //:bump-openroad` --
  bumps the tool to the latest upstream commit and builds it.
- `bazelisk run //:bump-orfs` -- bumps ORFS to the latest upstream
  commit, re-packages the flow scripts and all PDK tarballs.
- `bazelisk run //:release -- yosys|openroad|orfs|all` --
  uploads the built packages to GitHub Releases.

#### What `//:bump-yosys` does

1. **Resolves the latest upstream commit** for yosys and its
   submodules (ABC, cxxopts, yosys-slang, slang, fmt) by querying
   the GitHub API or running `git ls-remote`:
   ```sh
   git ls-remote https://github.com/The-OpenROAD-Project/yosys HEAD
   git ls-remote https://github.com/YosysHQ/abc HEAD
   # ... etc. for each submodule
   ```

2. **Updates `yosys/extension.bzl`** (or `yosys/private/versions.bzl`)
   with the new commit SHAs. Clears sha256 fields so Bazel
   re-downloads and computes fresh hashes on first build.

3. **Builds yosys from source** to verify the bump works:
   ```sh
   bazelisk build @yosys//:yosys @yosys//:yosys-abc @yosys//:yosys-share.tar
   ```

4. **Prints a summary** of what changed (old commit -> new commit for
   each component) and whether the build succeeded.

The human reviews the diff, runs any additional tests, and commits
the version bump.

#### What `//:bump-openroad` does

Same pattern:

1. **Resolves the latest upstream commit** from
   `The-OpenROAD-Project/OpenROAD.git` main branch.

2. **Updates `MODULE.bazel`** (the `git_override` commit for
   openroad) and clears the sha256 if present.

3. **Builds OpenROAD from source** to verify:
   ```sh
   bazelisk build @openroad//:openroad @openroad//src/sta:opensta
   ```

4. **Prints a summary** of old vs. new commit and build status.

Building from source is the whole point -- the bump target confirms
that the new upstream commit actually compiles before anyone cuts a
release.

#### What `//:bump-orfs` does

1. **Resolves the latest upstream commit** from
   `The-OpenROAD-Project/OpenROAD-flow-scripts.git` main branch:
   ```sh
   git ls-remote https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts HEAD
   ```

2. **Clones the ORFS repo** at the new commit into a temporary
   directory (or updates the existing Bazel cache).

3. **Packages the ORFS flow tarball** -- extracts only the files
   bazel-orfs needs:
   ```
   flow/Makefile
   flow/scripts/
   flow/util/
   flow/scripts/variables.yaml
   ```
   into `orfs-flow-<commit-short>.tar.gz`.

4. **Packages each PDK tarball** -- for each supported PDK (asap7,
   sky130hd, sky130hs, gf180, ihp-sg13g2, nangate45), extracts
   `flow/platforms/<pdk>/` into `<pdk>-<commit-short>.tar.gz` with a
   generated `BUILD.bazel` containing the `orfs_pdk` rule.

5. **Computes sha256** for each tarball.

6. **Updates `private/versions.bzl`** (or equivalent) with the new
   ORFS commit, tarball URLs, and sha256 values.

7. **Builds a smoke test** to verify the new ORFS scripts work with
   the current yosys and OpenROAD:
   ```sh
   bazelisk build //:lb_32x128_synth
   ```

8. **Prints a summary** of what changed and the sha256 values for
   all generated tarballs.

The human reviews the diff and commits. The tarballs are uploaded
to GitHub Releases via `bazelisk run //:release -- orfs`.

#### What `//:release` does

The `//:release` target is a `sh_binary` (or `py_binary`) that:

1. **Builds or locates the artifacts** depending on what is being
   released:
   - `yosys`: builds from source via `bazelisk build @yosys//:yosys @yosys//:yosys-abc @yosys//:yosys-share.tar`
   - `openroad`: builds from source via `bazelisk build @openroad//:openroad @openroad//src/sta:opensta`
   - `orfs`: uses the tarballs already produced by `//:bump-orfs`
     (ORFS flow scripts + all PDK tarballs)

2. **Packages the outputs** into release tarballs:
   ```
   yosys-0.48-linux-x86_64.tar.gz
   openroad-2.0-19336-linux-x86_64.tar.gz
   orfs-flow-f40d2f3.tar.gz
   asap7-f40d2f3.tar.gz
   sky130hd-f40d2f3.tar.gz
   # ... etc. for each PDK
   ```
   For OpenROAD, the tarball includes bundled runtime libraries (Qt,
   TCL, Ruby) collected from the build outputs, with `RPATH` set to
   `$ORIGIN/../lib`.

3. **Computes sha256** for each tarball and prints them for inclusion
   in `private/versions.bzl`.

4. **Creates GitHub Releases** using `gh release create` with
   namespaced tags and uploads the tarballs as assets:
   ```sh
   gh release create yosys/v0.48 \
     --title "Yosys 0.48 (pre-built)" \
     --notes "Built from commit d3e297f with yosys-slang 64b4461" \
     yosys-0.48-linux-x86_64.tar.gz

   gh release create openroad/v2.0-19336 \
     --title "OpenROAD 2.0-19336 (pre-built, GUI enabled)" \
     --notes "Built from commit df79404 with GUI enabled" \
     openroad-2.0-19336-linux-x86_64.tar.gz

   gh release create orfs/vf40d2f3 \
     --title "ORFS flow scripts (f40d2f3)" \
     --notes "Flow scripts and makefiles from ORFS commit f40d2f3" \
     orfs-flow-f40d2f3.tar.gz

   # One release per PDK, all under the same ORFS commit
   gh release create pdk/asap7/f40d2f3 \
     --title "asap7 PDK (f40d2f3)" \
     asap7-f40d2f3.tar.gz
   # ... etc.
   ```

5. **Prints the `versions.bzl` update** -- the sha256 values and URLs
   to paste into the version pinning file. The human reviews and
   commits this change.

#### Example usage

```sh
# Build and release yosys pre-built binaries
bazelisk run //:release -- yosys

# Build and release OpenROAD pre-built binaries
bazelisk run //:release -- openroad

# Package and release ORFS flow scripts + all PDK tarballs
bazelisk run //:release -- orfs

# Release everything
bazelisk run //:release -- all
```

The target reads version information (commits, version strings) from
the existing module extension configuration, so there is no manual
version entry.

#### Access permissions

The `gh release create` step requires GitHub write access to the
`The-OpenROAD-Project/bazel-orfs` repository:

| Who               | Permission needed              | How                          |
|-------------------|--------------------------------|------------------------------|
| **Maintainer (human)** | `contents: write` on bazel-orfs | GitHub repo collaborator or team membership with write role. The `gh` CLI authenticates via `gh auth login` or `GITHUB_TOKEN` env var. |
| **CI (GitHub Actions)** | `contents: write` on the workflow | Set `permissions: contents: write` in the workflow YAML. The default `GITHUB_TOKEN` for the repo has this if the workflow is in the same repo. |

No special PATs or bot accounts are needed -- the default GitHub
token for Actions workflows in `bazel-orfs` already has `contents:
write` permission, which covers creating releases and uploading
assets.

For manual releases from a developer workstation, the human must:
1. Be a collaborator with write access on `bazel-orfs`.
2. Have `gh` CLI authenticated (`gh auth login` or `GITHUB_TOKEN`).
3. Run `bazelisk run //:release -- yosys` (or `openroad` or `all`).

The `//:release` target **never pushes git commits** -- it only
creates GitHub Releases with asset uploads. Version pinning updates
(`private/versions.bzl`) are printed to stdout for the human to
review and commit separately.

#### CI automation (optional)

A GitHub Actions workflow can automate the release on tag push:

```yaml
name: Release pre-built binaries
on:
  push:
    tags:
      - 'yosys/v*'
      - 'openroad/v*'
      - 'orfs/v*'
      - 'pdk/*/v*'

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - name: Build and upload
        run: bazelisk run //:release -- ${GITHUB_REF_NAME%%/*}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Push a tag like `yosys/v0.48` or `orfs/vf40d2f3` and the workflow
builds and uploads to a matching GitHub Release. The human then
updates `versions.bzl` with the printed sha256 values.

### Build matrix

Pre-built binaries target Ubuntu linux-x86_64 as the primary platform.
GUI support (Qt, OpenGL) limits portability -- bundling Qt for every
platform is non-trivial and the user base is overwhelmingly Ubuntu.

| Platform     | Pre-built | OpenROAD GUI | Notes                              |
|--------------|-----------|--------------|------------------------------------|
| linux-x86_64 | Yes       | Yes          | Primary. Ubuntu 22.04, GUI enabled.|
| linux-aarch64| No        | No           | Source build. Takes time, no config.|
| macos-arm64  | No        | No           | Source build. Takes time, no config.|

Users on unsupported platforms fall back to building from source. This
is slow (30-60+ minutes for OpenROAD, 10-20 for yosys) but requires
no special configuration -- the module extension detects that no
prebuilt is available for the host platform and automatically uses the
source build path. The source-built OpenROAD omits GUI support since
Qt cross-platform packaging is non-trivial; batch RTL-to-GDS flows
work fully without it.

Each tarball is self-contained:

```
yosys-<version>-linux-x86_64/
  bin/yosys
  bin/yosys-abc
  share/yosys/         # techmap, plugins (including slang.so)

openroad-<version>-linux-x86_64/
  bin/openroad
  bin/opensta
  lib/                 # bundled Qt, TCL, Ruby shared libraries
```

The OpenGL driver is the one host dependency -- it comes from the
system mesa/GPU driver and cannot be bundled.

### Prebuilt repository rule (shared pattern)

```python
# yosys/prebuilt.bzl (openroad/prebuilt.bzl follows the same pattern)

_PLATFORMS = {
    "linux-x86_64": struct(
        url = "...releases/download/yosys/v{version}/yosys-{version}-linux-x86_64.tar.gz",
        sha256 = "...",
        exec_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
    ),
    # Other platforms: no prebuilt available, fall back to source build.
}

def _yosys_prebuilt_impl(repository_ctx):
    # Detect host platform; if no prebuilt match, fail with a message
    # directing the module extension to use the source build path.
    repository_ctx.download_and_extract(url = ..., sha256 = ...)
    repository_ctx.symlink(repository_ctx.attr._build_file, "BUILD.bazel")

yosys_prebuilt = repository_rule(...)
```

The module extension detects the host platform and chooses prebuilt
(linux-x86_64) or source build (everything else) automatically. No
user configuration needed either way.

---

## Migration path

1. **Phase 1 -- Toolchain types**: Add `toolchain.bzl` with providers
   and toolchain rules for both yosys and OpenROAD. Register toolchains
   backed by the existing source-built repositories. Update rules to
   resolve via `ctx.toolchains[...]`. Keep `global_config` entries as
   deprecated aliases.

2. **Phase 2 -- Pre-built tool releases**: Set up `//:bump-yosys`,
   `//:bump-openroad`, and `//:release` targets. Produce pre-built
   release tarballs for yosys and OpenROAD on linux-x86_64. Add
   `prebuilt.bzl` repository rules. Make module extensions default to
   prebuilt, with source as opt-in fallback.

3. **Phase 3 -- ORFS and PDK packages**: Set up `//:bump-orfs` and
   extend `//:release` to handle ORFS flow scripts and per-PDK
   tarballs. Replace the ORFS `git_override` with tarball downloads.
   Move `orfs_pdk` BUILD definitions from ORFS patches into
   bazel-orfs itself.

4. **Phase 4 -- Clean up**: Remove `CONFIG_YOSYS` / `CONFIG_YOSYS_ABC`
   / `CONFIG_YOSYS_SHARE` / `CONFIG_OPENROAD` / `CONFIG_OPENSTA` /
   `CONFIG_MAKEFILE` / `CONFIG_PDK` from `global_config.bzl`. Remove
   legacy tool attributes from rule definitions. Clean up
   `yosys_repo.bzl`. Prune all remaining `@docker_orfs` vestiges:
   `stub.bzl`, default labels in `config.bzl`, private fallback
   attributes in `private/attrs.bzl`, and stale references in
   documentation and log files. Remove the ORFS patch stack
   (`patches/`).

5. **Phase 5 -- Retire**: When upstream tools publish proper Bazel
   modules on the BCR with pre-built binaries, deprecate our stop-gap
   toolchains and packages. Migrate users to the upstream modules.
   Delete the `yosys/` and `openroad/` submodules.

---

## User-applied patches (building from source)

Users who need to push past issues in upstream OpenROAD or yosys can
build from source with patches applied. This is a core workflow:
bazel-orfs itself maintains a patch stack against ORFS and OpenROAD
(see `patches/` and `openroad-visibility.patch`) to work around
upstream issues. These patches are pruned as fixes -- often articulated
differently -- land upstream and become unnecessary.

Downstream users follow the same pattern for their own needs.

### OpenROAD patches

Bazel's `git_override` supports a `patches` list. A user who needs a
custom OpenROAD adds this to their root `MODULE.bazel`:

```python
bazel_dep(name = "openroad")
git_override(
    module_name = "openroad",
    commit = "df79404cd806cc435b3c3b53678ebf2441c31313",
    init_submodules = True,
    patch_strip = 1,
    patches = [
        # bazel-orfs's own required patch
        "@bazel-orfs//:openroad-visibility.patch",
        # user's own patches
        "//:patches/openroad-fix-drt-crash.patch",
        "//:patches/openroad-add-metric-hook.patch",
    ],
    remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",
)
```

Patches are applied in order using `patch -p1`. Only the root module's
`git_override` takes effect (Bazel ignores non-root overrides), so the
user must include bazel-orfs's required patches alongside their own.

The same mechanism is used in
[ORFS PR #4094](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/pull/4094),
which maintains a patch stack against ORFS to push past integration
issues. As individual fixes land upstream, the corresponding patches
are dropped.

### Yosys patches

The yosys source build uses `repository_ctx.download_and_extract()`
rather than `git_override`, so there is no built-in `patches` attr
today. Users who need to patch yosys have two options:

1. **Fork and point at a custom commit** -- override the yosys commit
   in the module extension tag:

   ```python
   yosys = use_extension("@bazel-orfs-yosys//:extension.bzl", "yosys_ext")
   yosys.default(
       yosys_commit = "abc123...",  # commit on user's fork
   )
   ```

2. **Add patch support to `yosys_sources()`** -- extend the repository
   rule to accept a `patches` attr (like `git_override` does) and apply
   them after extraction. This is a small addition:

   ```python
   # In yosys_sources repository rule implementation:
   for patch in repository_ctx.attr.patches:
       repository_ctx.patch(patch, strip = 1)
   ```

   The module extension tag would gain a `patches` attribute:

   ```python
   yosys.default(
       patches = ["//:patches/yosys-fix-rtlil-parse.patch"],
   )
   ```

Option 2 should be implemented as part of this work -- it gives yosys
parity with the OpenROAD patching story.

### Prebuilt vs. patched source

When a user supplies patches, the toolchain must fall back to building
from source -- prebuilt binaries cannot incorporate arbitrary patches.
The module extension handles this automatically: if `patches` is
non-empty or `source(...)` is explicitly requested, it uses the source
repository rule instead of the prebuilt download.

This is the expected workflow:
1. Default users get fast prebuilt downloads.
2. Users pushing past upstream issues switch to source builds with
   patches.
3. As fixes land upstream and new prebuilt releases are cut, users
   drop their patches and return to prebuilts.

---

## Open questions

- **yosys-slang inclusion**: The current build compiles yosys-slang as a
  plugin. Prebuilt bundles must include it. Should we version yosys and
  yosys-slang independently or always ship them together?

- **OpenROAD bundled libraries**: Pre-built OpenROAD ships with GUI
  enabled, bundling Qt, TCL, and Ruby. Need to verify that `RPATH`-based
  resolution works reliably across Ubuntu versions (22.04, 24.04).
  OpenGL is the sole host dependency (mesa/GPU driver).

- **Remote execution**: For RBE, toolchains must be fully hermetic.
  The GUI-enabled prebuilt with bundled libraries should work if the
  RBE container has mesa installed. May need a headless (Xvfb) setup
  for GUI-dependent operations in CI.

- **Mock toolchains**: `mock/yosys/` and `mock/openroad/` provide
  Python-based mocks for fast testing. Should these be separate
  registered toolchains (with lower priority) or stay as rule-level
  attribute overrides?

- **Version policy**: Should toolchain versions track ORFS releases,
  upstream tool tags, or have independent versioning?

- **Additional prebuilt platforms**: Start with linux-x86_64 only.
  If demand justifies it, linux-aarch64 and macos-arm64 prebuilts
  can be added later. Users on those platforms build from source in
  the meantime -- it takes time but requires no configuration.

---

## Pinning and multi-registry artifact hosting

### Why pinning matters (recap)

As established in the Context section, caching and pinning are
complementary. Caching handles the common case automatically;
pinning handles the foundational-tool case intentionally. The
mechanisms below implement the pinning side -- letting users
declare exactly which tool binary to use and when to upgrade.

The Docker-based approach (Phase 0 / current state) also suffers
from coupling: a single monolithic image conflates tool versions
with base OS and library versions, making it hard to pin one tool
without pulling in everything else.

### The pin is the sha256, not the URL

The core abstraction: a `(tool, version, platform)` triple resolves
to a URL + sha256, independent of where the artifact lives. Two
users pointing at different URLs but the same sha256 get the same
binary and the same Bazel cache behaviour. This makes the hosting
backend a deployment detail, not a build system concern.

`private/versions.bzl` is the single source of truth:

```python
# private/versions.bzl

PINNED = {
    "openroad": {
        "version": "2.0-19336",
        "commit": "66c2b5ed03ea15f4ab7631537c9380d8239ec67a",
        "platforms": {
            "linux-x86_64": {
                "sha256": "abc123...",
                "urls": [
                    # Primary: bazel-orfs GitHub Releases (public)
                    "https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/openroad/v2.0-19336/openroad-2.0-19336-linux-x86_64.tar.gz",
                ],
            },
        },
    },
    "yosys": {
        "version": "0.48",
        "commit": "...",
        "platforms": {
            "linux-x86_64": {
                "sha256": "def456...",
                "urls": [
                    "https://github.com/The-OpenROAD-Project/bazel-orfs/releases/download/yosys/v0.48/yosys-0.48-linux-x86_64.tar.gz",
                ],
            },
        },
    },
}
```

The `urls` list is tried in order by `repository_ctx.download`, so
users can prepend a private mirror and fall back to the public
release.

### Artifact source overrides in MODULE.bazel

Users override the artifact source without changing rule definitions:

```python
# Public GitHub Releases (default -- no override needed)
orfs.default()

# Private GitHub Releases (fork with proprietary patches)
orfs.default(
    openroad_urls = [
        "https://github.com/my-org/bazel-orfs/releases/download/openroad/v2.0-19336-patched/openroad-2.0-19336-patched-linux-x86_64.tar.gz",
    ],
    openroad_sha256 = "...",
)

# Google Artifact Registry / Cloud Storage
orfs.default(
    openroad_urls = [
        "https://storage.googleapis.com/my-bucket/openroad/v2.0-19336/openroad-linux-x86_64.tar.gz",
    ],
    openroad_sha256 = "...",
)

# Any HTTPS endpoint (S3, Artifactory, internal mirror)
orfs.default(
    openroad_urls = [
        "https://artifacts.example.com/openroad/v2.0-19336/openroad-linux-x86_64.tar.gz",
    ],
    openroad_sha256 = "...",
)
```

### Supported hosting backends

All backends use the same `urls` + `sha256` download mechanism.
The difference is authentication:

| Backend | Auth mechanism | Notes |
|---------|---------------|-------|
| **Public GitHub Releases** | None | Default. CDN-backed, immutable, 2 GB/asset limit. |
| **Private GitHub Releases** | `GITHUB_TOKEN` env var with `contents:read` | `--repo_env=GITHUB_TOKEN` in `.bazelrc`. Repository rule passes token as auth header. |
| **GCR / Artifact Registry** | `--credential_helper` or ambient ADC | Standard Bazel credential helpers handle GCP auth. No bazel-orfs changes needed. |
| **S3 / generic HTTPS** | `--credential_helper` or pre-signed URLs | Pre-signed URLs work without any auth config. |

Private GitHub Releases require the repository rule to pass the
token:

```python
def _prebuilt_impl(repository_ctx):
    token = repository_ctx.os.environ.get("GITHUB_TOKEN", "")
    auth = {}
    if token:
        auth = {url: {
            "type": "pattern",
            "pattern": "token %s" % token,
        } for url in urls}

    repository_ctx.download_and_extract(
        url = urls,
        sha256 = sha256,
        auth = auth,
    )
```

For GCR and other backends, Bazel's built-in `--credential_helper`
handles auth transparently -- no changes in bazel-orfs rules.

### Build, pin, and share your own binaries

Users who need custom patches build from source once, then pin
and distribute the result:

```bash
# 1. Build from source with patches (one-time or in CI)
bazelisk build @openroad//:openroad  # with git_override patches in MODULE.bazel

# 2. Package into a release tarball
bazelisk run //:package-openroad
# Prints: openroad-2.0-19336-mypatch-linux-x86_64.tar.gz  sha256:abc123...

# 3. Upload to your artifact host
gh release create openroad/v2.0-19336-mypatch \
  openroad-2.0-19336-mypatch-linux-x86_64.tar.gz \
  --repo my-org/my-repo

# 4. Pin in MODULE.bazel
# orfs.default(
#     openroad_urls = ["https://github.com/my-org/my-repo/releases/download/..."],
#     openroad_sha256 = "abc123...",
# )
```

This workflow gives full control: apply arbitrary patches, build
once, pin the result, and share across team and CI. The sha256
guarantees everyone gets the exact same binary regardless of which
URL they download from.

### Changes required for pinning support

Most of the infrastructure already described in this document
(prebuilt repository rules, versions.bzl, module extension tags)
directly serves pinning. The additional pieces specific to
multi-registry support:

1. **`extension.bzl`** -- Add `openroad_urls`, `openroad_sha256`,
   `yosys_urls`, `yosys_sha256` optional attributes to
   `orfs.default()`. When set, these override the defaults in
   `versions.bzl`.

2. **`prebuilt.bzl`** -- Read `GITHUB_TOKEN` from environment for
   private GitHub Release authentication. Pass through to
   `repository_ctx.download_and_extract(auth=...)`.

3. **`//:package-openroad`**, **`//:package-yosys`** (new) --
   Build targets that produce relocatable tarballs (RPATH-patched,
   bundled shared libs) suitable for upload to any hosting backend.

4. **Documentation** -- Guide for private hosting setup: env var
   configuration, credential helpers, pre-signed URL patterns.
