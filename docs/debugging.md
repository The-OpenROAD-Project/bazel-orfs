# Debugging bazel-orfs

Hard-won, generalizable tips for debugging bazel-orfs builds, bumps, and the
from-source EDA stack (OpenROAD / yosys / sv-elab / ORFS). Most of these bite
during dependency bumps and slang-frontend work.

## Synthesis / yosys

### Unmask swallowed yosys/slang/abc errors with `YOSYS_FLAGS=`
The synth/canonicalize steps run `yosys $YOSYS_FLAGS`. The default
`YOSYS_FLAGS=-v 3` (and `-q`) can **suppress the actual error**, leaving only a
generic `ERROR: Compilation failed` — which the flow surfaces as
`Canonicalizing RTL for <module> failed` with no reason. Re-run the failing
target with `YOSYS_FLAGS=` (empty) to reveal the real diagnostic.

Observed: the same failing `read_slang` shows
`error: '--ignore-unknown-modules' no longer supported` only with
`YOSYS_FLAGS=`; at `-q` and `-v 3` it is hidden. (A hard error being gated by
verbosity is itself an upstream bug worth reporting.)

### Replay `read_slang` standalone
For a "Canonicalizing RTL for X failed", copy the exact `read_slang` command
from `results/**/logs/**/1_1_yosys_canonicalize.log` and run it directly:
`yosys -m <slang.so> -p "read_slang …"`. This isolates a slang-frontend failure
from the rest of the flow and lets you bisect the args (drop
`--ignore-unknown-modules`, `--empty-blackboxes`, `--keep-hierarchy` one at a
time). Build the plugin + yosys with
`bazelisk build @sv-elab//src/yosys_plugin:slang.so @yosys//:yosys`.

### Per-module canonicalization isolates failures
bazel-orfs canonicalizes each kept module separately ("Canonicalizing RTL for
`<module>`" / "Re-canonicalize for partition cache: `<module>`"), blackboxing the
others by name. The module named in the error is the unit to attack; combine
with `YOSYS_FLAGS=` to see the underlying error.

### Two independent slang consumers — don't conflate
1. **OpenROAD's in-tree `src/syn` elaborator** — the `third-party/slang-elab`
   submodule + the `@slang` → `@sv-lang` alias.
2. **The yosys plugin `slang.so`** — from BCR `sv-elab`, exposed via
   `orfs.default(yosys_plugins=[…])` → `YOSYS_PLUGIN_PATH`.

RTL canonicalization uses the plugin (2). `Can't load module './slang': …
cannot open slang.so` means the plugin isn't wired (yosys fell back to its
`share/plugins` dir); set `yosys_plugins`.

## Builds & the from-source toolchain

### "up-to-date, 0 processes" is a cache hit, not a compile
`bazel build //:openroad` showing `up-to-date … N action cache hit` reused a
prior (often cross-session disk-cache) build of that exact commit. To actually
exercise a bumped commit, build a flow target that *runs* the tool (e.g. a
`*_synth`), which forces the exec-config compile.

### Pipeline exit codes mask failures
`bazelisk build … | tee log; echo done` returns the exit of the **last**
pipeline element, so a failed or target-not-found build can read as exit 0. Use
`${PIPESTATUS[0]}`, or grep the log for `Build did NOT complete successfully` /
`FAILED`.

### Hermetic-toolchain registration is per-root
A root that builds OpenROAD from source but does not
`register_toolchains("@llvm//toolchain:all")` falls back to the host compiler and
can hit host-glibc issues (e.g. glibc-2.41 `@scip`/`tinycthread`). A host-gcc
error in a from-source build usually means the hermetic LLVM toolchain isn't
registered in that workspace.

## Dependency bumps

### `--head=openroad` bumps to origin/master
`bazelisk run //:bump -- --head=openroad` bumps ORFS to master and pins OpenROAD
to its own `origin/master` HEAD, regenerating the archive_override integrity +
submodule `patch_cmds`.

### Master bumps surface stale carried patches
A carried patch failing with `CONTENT_DOES_NOT_MATCH_TARGET` usually means
upstream absorbed or moved it. Diff the new upstream file and **retire** the
patch if it's redundant.

### Direct-dependency drift
A master bump pulls newer transitive versions; `root requires X but got Y`
warnings mean you should sync the direct-dep pins (e.g. `rules_cc`, `abc`,
`glpk`) and any lockstep maps (yosys ↔ abc in `bump.py`).

### `--lockfile_mode=off`
This repo runs with `--lockfile_mode=off`, so there is no `MODULE.bazel.lock` to
regenerate; `bazel mod tidy` only validates resolution and rewrites `use_repo`.

## Overrides (`archive_override` / local checkouts)

### `patches` run before `patch_cmds`
In an `archive_override`, `patches` apply to the base tarball first; `patch_cmds`
run afterward (and are what vendor submodules). A fix to a `patch_cmds`-vendored
submodule (e.g. `third-party/slang-elab`) must itself be a `patch_cmds` step
(`git apply` / `sed`), not a `patches` entry.

### Local overrides skip `patch_cmds`
`--override_module` / `local_path_override` use the working tree as-is — the
archive's submodule vendoring and the `@slang` → `@sv-lang` sed do **not** run.
Apply those fix-ups by hand when iterating on a local OpenROAD checkout, e.g.
`common --override_module=openroad=/path/to/OpenROAD` in `user.bazelrc`.

### A module override must keep the module's declared name
`archive_override(module_name = "foo", …)` fails with *"declares a different
name"* if the tarball's `MODULE.bazel` says `module(name = "bar")`. Renamed
upstreams (e.g. `yosys-slang` → `sv-elab`) need the `bazel_dep` name changed
too, not just the archive URL.

### Extension-tag labels must resolve even when the module is a dependency
A label in `orfs.default(yosys_plugins=[@sv-elab//…])` must be visible to the
module that declares the tag even when that module is consumed as a
**dependency** (only the root's tags are honored, but the label still has to
resolve). So the backing `bazel_dep` must be **non-dev** — dev deps are dropped
for non-root modules.
