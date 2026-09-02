# Plan: ORFS as a pure file store

> Written by Claude with Øyvind Harboe, from the module graph as it
> stands: ORFS `8c0616910`, bazel-orfs `main`, OpenROAD's
> `MODULE.bazel` at the commit ORFS's submodule points to. Section 3 is
> the constraint that decides the design; everything else follows from
> it. Claims not yet proven by a running build are marked
> **(unproven)** and are the content of step A4.

---

## 1. What we want

OpenROAD-flow-scripts is an **immutable store of reference designs,
scripts, PDKs and metadata**. That is what it is good at, and what its
maintainers curate. It is not a build system and its CI does not run
one: nothing in ORFS's `.github/workflows/` invokes bazel.

bazel-orfs is where the knowledge of *how to build* ORFS lives. Today
that knowledge is split across the module boundary, and the ORFS half
has to be maintained by people who do not use it.

Three things should be true:

1. **ORFS carries no bazel files.** Not fewer -- none.
2. **bazel-orfs does all the patching**, for every root module.
3. **OpenROAD picks the ORFS version and carries no patches.**

Point 3 is the sharp one. It is not a preference; it is the difference
between a design that can ship and one that needs a coordinated
upstream PR every time an ORFS file moves.

## 2. The coupling is 8 labels wide

Measured, not estimated. Every `@orfs//` reference in bazel-orfs:

```
@orfs//flow:asap7                      # orfs_pdk target
@orfs//flow:makefile                   # filegroup
@orfs//flow:makefile_yosys             # filegroup
@orfs//flow:scripts/synth.tcl          # exports_files
@orfs//flow:scripts/variables.yaml     # exports_files
@orfs//flow:platforms/asap7/lef/...    # exports_files glob
@orfs//flow:platforms/asap7/lib/...    # exports_files glob
@orfs//flow/designs/asap7/gcd          # design package
```

All of them are produced by `flow/BUILD` plus the design BUILD files.
And **OpenROAD does not reference `@orfs//` at all** outside its
`MODULE.bazel` -- no BUILD, no `.bzl`. It declares the dependency purely
so *bazel-orfs* can resolve those 8 labels when OpenROAD is the root
module.

So bazel-orfs is the sole consumer of ORFS's entire bazel surface:

| in ORFS | what it is | read by |
|---|---|---|
| 172 `flow/designs/*/BUILD` | 56 uniform `design()`, 89 `files()`, 28 custom | bazel-orfs only |
| `flow/designs/design.bzl` | the DSL -- already only a re-export, via patch 0046 | bazel-orfs only |
| `flow/BUILD` | `orfs_pdk` x 6, 2 filegroups, `exports_files` over `platforms/**` | bazel-orfs only |
| `flow/util/BUILD`, `BUILD.bazel`, `bazel/` | py_tests and helpers | nothing in CI |
| `MODULE.bazel` | 6 deps, 5 overrides, the `orfs` extension, `orfs_designs` | bazel-orfs only |

## 3. The rule that decides the design

**`patches` on `archive_override` / `git_override` is honoured only from
the root module.** Non-root override directives are no-ops. ORFS's own
`MODULE.bazel` says so in three places, from having been bitten by it:

> `single_version_override` is root-honored only

> Dev dependencies (only honoured when @orfs is the root module)

> Only the `git_override` below (implicitly root-only) is dev-conditional

Apply that to `bazel_dep(name = "orfs")`:

- **OpenROAD is root** -> only OpenROAD can patch ORFS. That is point 3,
  violated.
- **bazel-orfs is non-root** -> its overrides are ignored. It cannot do
  the job at all.

There is no arrangement of overrides that satisfies point 3, because the
mechanism is root-scoped by design. As long as ORFS is consumed as a
bzlmod module, the patching lands on whoever is root.

**Module extensions have the opposite property.** They run for every
build regardless of which module declared them. A repository created by
a bazel-orfs module extension is fetched and patched by bazel-orfs's
code, root or not.

That is the whole argument for `http_archive`. It is not a stylistic
preference over `bazel_dep`; it is the only mechanism that puts the
patching where we need it.

## 4. The design

ORFS becomes a repository created by bazel-orfs's existing
`orfs_repositories` extension:

```python
# in bazel-orfs's extension.bzl
http_archive(
    name = "orfs",
    urls = [...],            # from the source tag
    integrity = ...,         # from the source tag
    strip_prefix = ...,
    patches = [...],         # bazel-orfs's own patches
    patch_cmds = [...],      # bazel-orfs generates BUILD files
)
```

and version selection moves from an override to a **tag**:

```python
# in OpenROAD's MODULE.bazel
orfs = use_extension("@bazel-orfs//:extension.bzl", "orfs_repositories")
orfs.source(commit = "8c0616910...", integrity = "sha256-...")
```

`use_repo(orfs, "orfs")` keeps the apparent name, so all 8 labels above
are spelled exactly as they are today. Nothing in bazel-orfs's rule
code changes.

This follows the precedent `orfs.default()` already set: the extension
reads `module_ctx.modules[0].tags`, i.e. the root module's tags, so
"the root picks the version" is the existing contract, not a new one.

**OpenROAD's `MODULE.bazel` gets smaller.** Today:

```python
ORFS_COMMIT = "afad87da..."
bazel_dep(name = "orfs", dev_dependency = True)
archive_override(
    module_name = "orfs",
    sha256 = "3b61b0cb...",
    strip_prefix = "OpenROAD-flow-scripts-" + ORFS_COMMIT,
    urls = ["https://github.com/.../archive/" + ORFS_COMMIT + ".tar.gz"],
)
```

After: one `orfs.source()` tag. No patches, no `strip_prefix`, no URL
construction. The OpenROAD PR *removes* lines -- which is the right
shape for a PR to an inundated maintainer.

### bazel-orfs exports the PDKs

`orfs_pdk` lives in ORFS's `flow/BUILD` today because a `glob()` only
sees its own repository. Under `http_archive` **bazel-orfs authors that
BUILD file**, and the glob then runs in the ORFS repo context. So

```python
[orfs_pdk(name = pdk, srcs = glob(["platforms/{pdk}/**/*.{ext}"...]))]
```

moves here, together with the per-platform extension map (`asap7`:
`cfg gds lef lib lib.gz lyt mk rules sdc sv tcl v`, and so on). That map
is a statement about how the rules consume a PDK, so it belongs beside
the rules rather than in the file store.

Same for the `makefile` / `makefile_yosys` filegroups and the
`exports_files(glob(["platforms/**/*"]))` that makes individual PDK
files addressable.

### What is generated vs patched

| surface | mechanism | why |
|---|---|---|
| 56 uniform design BUILDs | **generated** (`patch_cmds`) | body is a constant |
| 89 `files()` BUILDs | **patched** | the group name is not derivable -- see below |
| 28 custom design BUILDs | **patched** | genuinely per-design |
| `flow/BUILD` (PDKs, filegroups, exports) | **generated** from the platform list | mechanical |
| `flow/util/BUILD`, `BUILD.bazel`, `bazel/` | **dropped** | nothing consumes them |

The `files()` group names are not derivable, and this is worth recording
because it looks derivable and is not. `files("verilog")` vs
`files("include")` is decided by which label *other* designs reference,
not by what the directory holds: `src/cva6` declares `files("verilog")`
while holding no `.v` or `.sv` at all, and `prim/rtl` holds both `.sv`
and `.svh` but declares `files("include")`. A generator that guesses
renames a target, and the breakage surfaces in some unrelated design's
config. `test/orfs_design_builds_test.py` found 24 such disagreements
and is what keeps the generator honest.

## 5. Why bump-and-fix is the right trade

The file layout of ORFS is very stable, and the coupling is deliberate
and tight. When an ORFS bump breaks a design here, fixing it in
bazel-orfs is cheap -- these designs exist for experiments, not for
production tapeouts.

So the testing policy is deliberately narrow:

- **Keep the load guard.** CI runs
  `bazelisk query '@orfs//flow/designs/...:*'`. It costs seconds and it
  catches the class of failure that actually hurt us: the DSL drifting
  out of step with the rules it drives, which made *every* design
  package fail to load with `orfs_design() got unexpected keyword
  argument: blender` and went unnoticed because nothing built `@orfs`
  designs from a bazel-orfs workspace.
- **Build only a few small asap7 designs.** Enumerated explicitly in
  `test/BUILD`'s `ORFS_TESTS`, starting with
  `@orfs//flow/designs/asap7/gcd:gcd_test`, and grown only when a
  feature earns regression coverage.
- **Do not attempt broad design coverage.** A design that breaks on a
  bump is a bazel-orfs fix, not an incident. Paying CI time to discover
  breakage we are happy to fix on demand buys nothing.

The load guard and the small build set answer different questions:
"can bazel still see every design?" and "does the flow still run?".
The first must never break, because it breaks everything at once. The
second is allowed to.

## 6. Consequences and limits

- **Root-only tags.** `module_ctx.modules[0]` is the root module, so a
  non-root consumer cannot pick an ORFS version -- it gets bazel-orfs's
  default. Acceptable: OpenROAD and ORFS are the roots that care. Stated
  as a limit rather than worked around.
- **`bazel_dep(name = "orfs")` must go** from bazel-orfs and from
  OpenROAD: an extension-created repo and a module cannot both be
  `orfs`. This also removes the awkward exception in ORFS's
  `MODULE.bazel`, where the bazel-orfs dep is deliberately *not*
  dev-only just so `flow/BUILD` can load `orfs_pdk` at non-root
  consumption.
- **ORFS stays a bazel module.** `http_archive` ignores `MODULE.bazel`
  entirely, so ORFS may keep one and remain consumable as a module by
  anyone who wants that. We simply stop consuming it that way. The two
  goals are compatible; only *our* dependency edge changes.
- **(unproven)** `http_archive` inside a module extension taking
  `patches` as labels. The repo rule accepts label patches, but an
  extension resolves labels through its own repo mapping; if that does
  not work, patching falls back to `patch_cmds` shell, which this design
  already leans on for BUILD generation.
- **(unproven)** that a generated `flow/BUILD` reproduces the current
  PDK targets exactly. The check is a target-list diff, described below.

## 7. Steps

**A1** This document.

**A2** Merge #881 (the estimation-ladder findings; unrelated, just open).

**A3** Bump the ORFS pin `427bd762` -> `8c0616910` (55 commits) with
`bump.py`. Exercises the load guard against churn it has never seen, and
measures how cheap bump-and-fix actually is before the design bets on it.

**A4** The spike, and the only step that can fail interestingly:
`orfs.source()` tag, `http_archive` in the extension,
`use_repo(orfs, "orfs")`, generated `flow/BUILD` and design BUILDs.
Success criterion: `bazelisk build
@orfs//flow/designs/asap7/gcd:gcd_final` with **ORFS's own bazel files
deleted from the fetched tree** -- the honest test of "zero bazel
surface", rather than of "we patched over them".

**A5** Narrow CI per section 5: keep the load guard, pick 2-3 small
asap7 designs by measured runtime.

**B** ORFS PR: delete the whole bazel surface from section 2. One PR,
one review. Verification in the body is a target-list diff --
`bazelisk query '@orfs//flow/designs/...:*'` before and after, expected
byte-identical at 3,889 targets -- so a reviewer checks two lists
without needing to know bazel.

**C** OpenROAD PR: replace `bazel_dep` + `archive_override` with one
`orfs.source()` tag. Removes lines; carries no patches. Independent of
B's timing.

## 8. What would make this the wrong design

Recorded so it can be revisited on evidence rather than re-argued:

- If ORFS's own CI started running bazel, its bazel files would have a
  first-party reader and should stay.
- If ORFS's file layout became unstable, the generated `flow/BUILD` and
  the patch stack would turn into the maintenance burden this design is
  meant to remove. The bet in section 5 is specifically that the layout
  is stable.
- If a third consumer appeared that needs `@orfs` as a module *and*
  needs it patched, root-only tags would stop being sufficient.
