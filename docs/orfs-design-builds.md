# ORFS design BUILD files

ORFS carries ~173 BUILD files under `flow/designs/`, and ~150 of them say
nothing but which kind of files the directory holds:

| count | body |
|---|---|
| 81 | `files("verilog")` |
| 56 | `design(config = "config.mk")` |
| 8 | `files("lef")`, `files("lib")`, `files("gds")`, `files("include")` |
| ~18 | genuinely bespoke |

Their only reader is bazel, which ORFS does not itself use. bazel-orfs
now generates them, so ORFS can stop carrying them.

## What it is for

The normal use case of bazel-orfs is idiomatic Bazel: a project writes
`orfs_flow()` in its own BUILD file, next to its RTL and constraints, as
[examples/BUILD](../examples/BUILD) does. That is the product. The
`config.mk` DSL is the lab bench: it turns ORFS's own designs into Bazel
targets so that an experiment can be run across all of them from this
repository, with everything the experiment needs in a single pull
request.

One PR can carry an ORFS patch under `patches/`, an OpenROAD or Yosys
patch on its `archive_override`, a change to bazel-orfs itself, and be
judged against real designs by the CI steps that load and analyse every
`@orfs//flow/designs` flow target. The pieces are upstreamed one by one
when the churn is over, and the patches deleted here as they land. The
[README](../README.md#carry-patches-while-upstream-decides) describes
the patch-carrying side; this page describes the design side.

The ORFS designs are the right test bed for two reasons. They are
real: gcd through swerv_wrapper, six platforms, macros, hierarchy, the
designs ORFS's own QoR dashboard tracks. And the OpenROAD maintainers
know every pebble on that beach. A shift in `ibex` on asap7 or `aes` on
nangate45 is recognised at a glance for what it is, noise, regression
or improvement, in a way no private design can offer.

The canonical experiment is parameter tuning. `CORE_UTILIZATION`,
`CORE_MARGIN` and `PLACE_DENSITY` are human predictions standing where
measurements should be; the auto-floorplan targets measure them
instead. From this workspace, race candidate floorplans for as many
designs as the machine warrants:

```sh
bazelisk build --keep_going \
  @orfs//flow/designs/asap7/gcd:gcd_auto_floorplan_data \
  @orfs//flow/designs/asap7/ibex:ibex_core_auto_floorplan_data
```

then write each winner into the design's `config.mk` in an ORFS checkout
as ordinary variables, with the estimate JSON of that moment as the
receipt:

```sh
bazelisk run @orfs//flow/designs/asap7/gcd:gcd_auto_floorplan_pin ~/ORFS
```

[docs/auto_floorplan.md](auto_floorplan.md) covers the race, the pin and
the receipt; [docs/estimate.md](estimate.md#division-of-labor-recommendations-here-mechanics-in-orfs)
the division of labour with ORFS's pin machinery. The same shape fits
any theory that has to hold across designs rather than on one: a
synthesis engine A/B (the `_syn_*` and `_yosys_*` variants the DSL
emits), a repair_timing change, a new default for a flow variable.

What it is not: a supported way to build every ORFS design, a DSL for
describing your own project, or available downstream. Not all designs
are hooked up, an ORFS bump that upsets one is a fix here rather than
an incident, and the `@orfs_designs` repository only exists with
bazel-orfs as the root module (see the next section).

## Driving an ORFS design from bazel-orfs

The whole point of owning this knowledge here: an ORFS design can be built
and inspected from a bazel-orfs workspace, without an ORFS checkout.

```sh
bazelisk run @orfs//flow/designs/asap7/gcd:gcd_synth gui_synth
bazelisk run @orfs//flow/designs/asap7/gcd:gcd_final
bazelisk test @orfs//flow/designs/asap7/gcd:gcd_test
```

Note the path: designs live under **`flow/designs/`**, not `designs/`.
`@orfs//designs/asap7/gcd` fails with

```
no such package '@@orfs+//designs/asap7/gcd': BUILD file not found
```

`gui_<stage>` works because the stage rules put the Qt-linked
`openroad_qt` into `DefaultInfo.runfiles` for exactly this, while keeping
it out of build actions -- so the GUI is available to `bazelisk run`
without forcing a Qt-linked binary into every build. The first invocation
builds OpenROAD with Qt, which is not quick; later ones are cached.

## How generation works

A `patch_cmds` step in bazel-orfs's `archive_override` for `@orfs` walks
`flow/designs` and writes a BUILD into any directory that has a
`config.mk` and no BUILD:

```python
load("@orfs_designs//:designs.bzl", "design")

design(config = "config.mk")
```

**Absent only — never overwritten.** That is the safety argument: a design
that needs a hand-written BUILD keeps it by virtue of having one. There is
no keep-list to maintain, nothing is silently clobbered, and the mechanism
is a no-op against an ORFS that still ships every BUILD.

## Why only `config.mk`, and not the `files()` groups

This was the plan at first, and measurement killed it. The `files()` BUILDs
declare a group name -- `"verilog"`, `"include"`, `"lef"`, `"lib"`,
`"gds"` -- and **which group a directory needs is not derivable from its
contents**:

- `src/cva6`, `src/mempool_group/rtl/axi` and 20 others declare
  `files("verilog")` while holding **no** `.v` or `.sv` at all -- only
  `.svh`, a `README.md`, or nothing. The filegroup is legitimately empty
  (`files()` globs with `allow_empty`), but the label still has to exist,
  because another design's `config.mk` references it.
- `src/ibex_sv/vendor/lowrisc_ip/prim/rtl` holds both `.sv` and `.svh`
  and declares `files("include")`, not `files("verilog")`.

The group is decided by what other configs reference. That information
lives in the config.mk corpus, not in the directory, and guessing it wrong
renames a target -- breaking references at the far end, in some other
design's config, which is a miserable thing to debug.

Generating them properly would mean precomputing the label set (bazel-orfs
already derives exactly these labels in its config parser) and shipping it
as data. That is a real option, at the cost of refreshing the list on ORFS
bumps. It is not done here.

So the cleanup is **56 files, not 150**. `test/orfs_design_builds_test.py`
holds the line: it compares the generator's rule against every canonical
BUILD ORFS still ships, and it is what caught the 24 disagreements that
scoped this down.

## Source directories ORFS never gave a BUILD

The recorded set (`orfs_design_builds.bzl`) covers the `files()` BUILDs
that existed when it was recorded. It cannot cover a source directory ORFS
adds later, and ORFS adds them without BUILDs because it does not run
bazel: `flow/designs/src/coralnpu/CoreMiniAxi.sv` arrived that way (ORFS
#4474), and `asap7/coralnpu` failed at analysis with

```
no such package '@orfs//flow/designs/src/coralnpu': BUILD file not found
```

For `flow/designs/src/**` the generator therefore *does* guess, absent-only:
`files("verilog")` if the directory holds any `.v` or `.sv`,
`files("include")` if it holds only `.svh`, nothing otherwise. This is not
the guessing the previous section refuses. That argument is about a
directory whose shipped BUILD the guess could contradict; here the rule
runs only where ORFS ships no BUILD and the recorded copy, written first,
has none either. `src/cva6` and `prim/rtl` keep their recorded names. Where
nothing exists at all, the choice is between a guessed package and no
package, and no package fails every design that references it.

The test's invariant for `src/` is stated exactly: every canonical
`files()` BUILD ORFS ships is either recorded verbatim or reproduced by
the rule. Run it against a real tree with `ORFS_DESIGNS_DIR` as described
in the test file.

## The ORFS cleanup PR

> Superseded in scope by
> [plans/orfs-as-file-store.md](plans/orfs-as-file-store.md): rather than
> deleting the 56 uniform BUILD files and keeping the rest, that plan
> removes ORFS's bazel surface entirely -- design BUILDs, `flow/BUILD`
> and `MODULE.bazel` -- as one PR. The verification recipe below still
> applies; only the file list grows.


### Delete

Every `flow/designs/**/BUILD` whose entire content, ignoring comments and
blank lines, is exactly:

```python
load("//flow/designs:design.bzl", "design")
design(config = "config.mk")
```

56 files at the currently pinned ORFS. Nothing else.

### Keep

- **Every `files(...)` BUILD** -- see above; the group name is not
  recoverable.
- **`flow/designs/design.bzl`** -- the bespoke BUILDs still load it.
- **`flow/designs/BUILD`** -- the `syn-dashboard` alias and
  `SYN_TEST_DESIGNS`.
- **`flow/BUILD`** -- `orfs_pdk` creates `//flow:asap7` and friends, which
  `design()` references as `pdk = "//flow:" + platform`. Those targets glob
  ORFS's platform files, so they cannot move out of ORFS without a separate
  change.
- **`bazel_dep(name = "bazel-orfs")` in MODULE.bazel** -- still required,
  for `orfs_pdk` above. Dropping it means moving `orfs_pdk` first.
- **The bespoke `design()` calls** carrying `user_arguments` or
  `local_arguments` (four of them), and `asap7/gcd`'s single-process flow
  test, which also references `@openroad`.

### Verify

Before and after, from a bazel-orfs workspace:

```sh
bazelisk query '@orfs//flow/designs/...:*' | sort > /tmp/targets.before
# ... apply the ORFS cleanup, bump the pin ...
bazelisk query '@orfs//flow/designs/...:*' | sort > /tmp/targets.after
diff /tmp/targets.before /tmp/targets.after
```

An empty diff is the acceptance criterion: the same targets, by name, from
generated BUILDs instead of carried ones. If generation guessed a
filegroup name wrongly the diff shows it, which is why this check matters
more than reading the generator.

`//test:orfs_design_builds_test` asserts the same property in CI against
whatever ORFS is pinned: for every design BUILD ORFS still ships whose
body is one of the canonical forms, the generator's rules pick the same
one.

### Rationale for ORFS reviewers

- Deletes bazel machinery ORFS does not use.
- No change to the `make` flow — these files are invisible to it.
- bazel consumers keep working, because bazel-orfs generates what it
  needs and the target list is unchanged (verified by the diff above).
