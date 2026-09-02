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

## The ORFS cleanup PR

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
