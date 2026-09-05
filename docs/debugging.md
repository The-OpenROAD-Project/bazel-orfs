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

## Reading stage logs

### Timestamp log lines with `--@bazel-orfs//:log_timestamps`
An ORFS log tells you what a stage did, not when. `Took N seconds:`
(`util.tcl`) and the closing `Elapsed time:` line are both written after the
fact, so a log that took four hours does not say which part of it took the
four hours.

    bazelisk build --@bazel-orfs//:log_timestamps //your:target_place

prefixes every logged line with elapsed wall seconds since the command
started:

    [    0.000] [INFO ODB-0227] LEF file: ..., created 13 layers
    [  184.421]      1300 |   0.0912 | 1.234560e+06 |  -0.31% | 4.12e+04 |
    [  391.887]      1310 |   0.0904 | 1.233210e+06 |  -0.11% | 4.28e+04 |

which is enough to see where the time actually went — a slow global-place
iteration, a `repair_timing` pass that stopped converging, a single
long-running command between two cheap ones.

Mechanically it replaces ORFS's `RUN_CMD` (`flow/scripts/variables.mk`, the
one variable every logged tool invocation goes through) with
`log_timestamps.py`, which delegates the actual work back to ORFS's
`run_command.py` and only adds the stamp and the log write. No ORFS patch is
involved, and every logged tool is stamped, not just OpenROAD.

Scope is the build actions — `bazelisk build` and `bazelisk test`. A tree
deployed by `//:deps` runs ORFS's own `RUN_CMD` and logs unstamped.

Two things to know:

* **It costs a rebuild.** Stamping changes the log bytes, so a stamped stage
  does not share cache entries with an unstamped one. This is a debugging
  flag, off by default; leaving it off is the normal state.
* **Stamps are read times, not emission times.** The clock is read as each
  line comes out of the child's pipe. OpenROAD's logger flushes as it goes,
  so the two coincide; a tool that block-buffers instead shows up as a burst
  of near-identical stamps — which is worth knowing in its own right.

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

## Host platform / older distributions

This section is about setting expectations, not about discouraging bug
reports. Please do file issues. The point of the checks below is to tell you
early which project can actually act on your failure, so you don't spend days
waiting on a fix that cannot come from here — a long walk down a windy beach
to a cafe that turns out to be closed.

### Check OpenROAD standalone first — it bounds what bazel-orfs can fix
bazel-orfs builds OpenROAD from source. If OpenROAD's own Bazel build does not
work on your host, there is nothing bazel-orfs can do about it: the rules here
orchestrate the flow, they don't influence how OpenROAD compiles. So build
[OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) on its own first:

```bash
git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git
cd OpenROAD
bazelisk build //:openroad //:openroad-qt //src/sta:opensta
```

All three are required by bazel-orfs. `openroad-qt` lands in the
`bazelisk run :<target>_<stage> gui_<stage>` runfiles, so it has to build even
for headless flows, and `//src/sta:opensta` is the OpenSTA binary bazel-orfs
runs (it lives in the `src/sta` submodule, hence `--recursive`).

That one command tells you where you stand:

- **All three build** — your failure is in bazel-orfs's own territory and an
  issue here is the right place for it.
- **Any of them fails** — the failure is upstream, and a bazel-orfs issue can
  only
  forward it. File it against OpenROAD with that command as the reproducer:
  it's a smaller, faster reproducer than an ORFS flow target, and it reaches
  the people who can fix it. Meanwhile, the bring-your-own-binary route below
  may get you running today.

yosys, abc, GNU Make and Qt come from their own modules, so they are additional
from-source surface beyond what this check covers.

### Bring your own OpenROAD when the from-source build won't go
If the standalone build fails on your host but you have a working OpenROAD
installed some other way (e.g. built with the classic CMake flow via
OpenROAD's `etc/DependencyInstaller.sh`), point bazel-orfs at it and skip the
from-source build entirely:

```starlark
orfs.default(
    openroad = "@bazel-orfs//:openroad",     # execs `openroad` from PATH
    openroad_qt = "@bazel-orfs//:openroad",  # only if that binary has the GUI
)
```

`@bazel-orfs//:openroad` is a two-line wrapper that `exec`s whichever
`openroad` is on `PATH`. Reuse it for `openroad_qt` only when the PATH binary
was built with GUI support; a headless build works for the flow stages but not
for `gui_<stage>`. This does not make the build hermetic and does not remove
the remaining from-source deps (yosys, abc, GNU Make), but it is often enough
to get a flow running on a host the full source build can't handle. See
[openroad.md](openroad.md), "Using a Locally Installed OpenROAD".

### No CI below ubuntu-22.04 — old distributions are unsupported in practice
bazel-orfs CI runs on `ubuntu-22.04` and nothing else
(`.github/workflows/ci.yml`). OpenROAD's Bazel CI runs on `ubuntu-latest` and
`macos-latest`. Neither project has a Bazel lane on an older or
enterprise-LTS distribution, so a fix that makes one of them build on such a
host can regress silently on the next dependency bump. Worth knowing before
you invest: individual snags on an old host are often fixable, but a
one-off fix is not a support promise, and the next bump can undo it.

Note that OpenROAD's *CMake* build supports considerably more platforms than
its Bazel build — `etc/DependencyInstaller.sh` covers RHEL/Rocky/Alma,
openSUSE and Debian. A distribution appearing there says nothing about the
Bazel path bazel-orfs uses; that combination is the bring-your-own case above.

## Dependency bumps

### `//:bump` only supports a pin 30 commit-days behind
A `bazel-orfs` pin more than 30 days behind the commit being bumped to is
refused outright — the migration paths for that shape are deleted, not
maintained. The span is between commit dates, so re-running later changes
nothing. The error names the
remedies; [Supported window](openroad.md#supported-window) has the details.

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
warnings mean you should sync the direct-dep pins (e.g. `rules_cc`, `abc`)
and any lockstep maps (yosys ↔ abc in `bump.py`).

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
