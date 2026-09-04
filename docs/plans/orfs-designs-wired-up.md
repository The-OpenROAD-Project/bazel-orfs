# Plan: every asap7 and sky130 ORFS design wired up

> Written by Claude with Øyvind Harboe from one failing build and an
> analysis-only sweep of every design under `flow/designs/asap7`,
> `flow/designs/sky130hd` and `flow/designs/sky130hs` at the pinned ORFS
> (`8c0616910`, 2026-09-01). Nothing in this document is implemented yet;
> section 7 is the proposal for approval. Where a claim rests on a build
> that has not been run, it says so.

---

## 1. What happened

```
bazelisk build @orfs//flow/designs/asap7/coralnpu:CoreMiniAxi_route
```

fails at analysis, before any tool runs:

```
ERROR: no such package '@@+orfs_repositories+orfs//flow/designs/src/coralnpu':
BUILD file not found in directory 'flow/designs/src/coralnpu' ...
referenced by '...//flow/designs/asap7/coralnpu:CoreMiniAxi_synth'
```

and, at load time, warns:

```
DEBUG: private/orfs_design.bzl:260:18: CoreMiniAxi sets SYNTH_HIERARCHICAL=1
with no SYNTH_KEEP_MODULES, so parallel synthesis will fail with
'per-module checkpoint missing'.
```

The first is fatal today. The second would be fatal the moment the first
is fixed. Neither is specific to coralnpu; both are gaps in how bazel-orfs
consumes an ORFS that no longer authors bazel files.

## 2. The sweep: 34 config.mk files, 32 flow targets

Every `config.mk` under the three platforms at the pin, against
`bazelisk build --nobuild --keep_going` of each design's `_route` target
(32 targets, 28 s of analysis):

| design | analysis | note |
|---|---|---|
| asap7/coralnpu | **fails** | A: `src/coralnpu` has no package. B: hierarchical, no kept list |
| asap7/aes-block | ok | B: hierarchical, no kept list (BLOCKS design) |
| asap7/riscv32i | ok | B: hierarchical, no kept list; **synth reproduced failing**, section 4 |
| asap7/riscv32i-mock-sram | ok | B: inherits riscv32i's config |
| sky130hd/microwatt | ok | B: hierarchical, no kept list |
| asap7/swerv_wrapper | ok | C: drops `$(CLKGATE_MAP_FILE)` from VERILOG_FILES, benign |
| asap7/minimal | no targets | by design: no VERILOG_FILES, recorded filegroup BUILD |
| asap7/riscv32i-mock-sram/fakeram7_256x32 | ok | block: its `fakeram7_256x32_synth` … `_generate_abstract` targets live in the parent package and analyse with the parent's `_route`; blocks have no route of their own |
| the other 26 | ok | aes, aes_lvt, aes-mbff, cva6, ethmac, ethmac_lvt, gcd, gcd-ccs, ibex, jpeg, jpeg_lvt, mock-alu, mock-cpu, tinyRocket, uart; sky130hd aes, chameleon, gcd, ibex, jpeg, riscv32i; sky130hs aes, gcd, ibex, jpeg, riscv32i |

"ok" means the action graph is declared without error. It does not mean
the flow runs green; only gcd and uart are built end to end in CI
(`ORFS_TESTS` in `test/BUILD`), and ORFS's own `flow/designs/asap7/BUILD`
lists designs that fail under OpenROAD-SYN. This plan is about wiring,
not QoR: a design is wired up when bazel can declare its actions and the
synth stage that starts them runs.

## 3. Problem A: a source directory ORFS never gave a BUILD

### Cause

`config_mk_parser` turns `$(DESIGN_HOME)/src/coralnpu/CoreMiniAxi.sv`
into the label `//flow/designs/src/coralnpu:CoreMiniAxi.sv`. That label
needs a package. bazel-orfs makes @orfs's design packages three ways
(`orfs_source.bzl`):

1. **generated** for any directory with a `config.mk` and no BUILD;
2. **recorded** verbatim for the 117 BUILDs ORFS shipped at the pin
   (`orfs_design_builds.bzl`), written back absent-only;
3. **patched** or written for `flow/BUILD` and `flow/designs/design.bzl`.

`flow/designs/src/coralnpu` is none of these. ORFS PR #4474 added the
design on 2026-08-25 with `CoreMiniAxi.sv` and no BUILD, because ORFS
does not run bazel and has no reason to write one. The recording was
made at this very pin and is complete; there was simply nothing to
record. `src/chameleon_hier` is in the same state (unreferenced today,
so it does not fail).

This is the systemic gap: **the recorded set covers what existed when it
was recorded, the generator covers config.mk directories, and every new
ORFS source directory falls between them.** `docs/orfs-design-builds.md`
explains why `files()` groups were not generated: for a directory that
*has* a shipped BUILD, the group name can disagree with the contents
(`src/cva6` declares `verilog` holding no `.v`; `prim/rtl` holds `.sv`
and declares `include`). That argument does not apply to a directory
with no BUILD at all. There, the choice is between a guessed package and
no package, and no package always fails.

### Fix (bazel-orfs)

Extend `_GENERATE_DESIGN_BUILDS` in `orfs_source.bzl` with a second,
absent-only rule for `flow/designs/src/**`:

- holds any `.v` or `.sv` → `files("verilog")`
- otherwise holds any `.svh` → `files("include")`
- otherwise → nothing

`files()` also exports each file as its own label, so both
`:CoreMiniAxi.sv` and `:verilog` resolve. The 117 recorded BUILDs still
win because they are written first and the generator skips any
directory that has one, so `src/cva6` and `prim/rtl` are untouched.

Tests to change with it:

- `test/orfs_design_builds_test.py::TestRules.test_file_groups_are_not_guessed`
  asserts the generator declines for `["gcd.v", "top.sv"]`. It inverts:
  the generator now guesses, and the docstring states the new invariant,
  that guessing is safe only where nothing shipped can disagree. The
  `prim/rtl` shape (`.sv` + `.svh`) becomes an explicit "would say
  verilog, which is why prim/rtl is recorded" case.
- `TestGeneratorAgreesWithOrfs` today compares only `design` forms. It
  extends to `files()` forms with the honest invariant: every canonical
  BUILD ORFS ships is either in `RECORDED_BUILDS` or reproduced by the
  rule.
- `TestGeneratorScript` gets a `src/<new>/x.sv` fixture and a
  `src/<new>/x.svh` fixture.
- `docs/orfs-design-builds.md` gets a paragraph on the src rule and why
  it is not the guessing the document warned against.

### Rejected

- **Add `flow/designs/src/coralnpu/BUILD` to ORFS.** Fixes one design and
  reintroduces the file class `docs/plans/orfs-as-file-store.md` is
  removing. The next new design fails the same way.
- **Hand-add an entry to `orfs_design_builds.bzl`.** The file is
  generated from a clean ORFS checkout and says so; a hand edit is the
  same one-design fix with a worse provenance story.
- **Derive the exact label set from the config.mk corpus** and generate
  only referenced packages. `@orfs_designs` already runs the parser, but
  it is a different repository from `@orfs`, whose BUILDs are written by
  `patch_cmds` at fetch time. Doing this properly means @orfs becoming a
  custom repository rule that downloads, parses and writes. It is the
  right end state if the content rule ever proves insufficient; the
  content rule is a fraction of the code and covers every shape seen so
  far.

## 4. Problem B: SYNTH_HIERARCHICAL=1 with no kept-module list

### Cause

Parallel synthesis declares one re-canonicalization action per kept
module, so the module names must be known at analysis time. With no
`SYNTH_KEEP_MODULES`, `private/orfs_design.bzl` still defaults
`SYNTH_NUM_PARTITIONS` to 32 and takes the parallel path; every
partition dies with `per-module checkpoint missing`. Commit `2b3e3a9`
reproduced this on nangate45/tinyRocket (all 32 partitions failed) and
`2bde78e` turned the analysis-time `fail()` into today's warning,
listing twenty ORFS designs in this state. Five of them are under the
three platforms here (section 2).

Reproduced again for this plan on the smallest of the five:

```
bazelisk build @orfs//flow/designs/asap7/riscv32i:riscv_top_synth
...
Wrote 16 kept modules to .../riscv_top/base/kept_modules.json
ERROR: Synthesizing partition 4/32 failed
ERROR: per-module checkpoint missing: .../partition_riscv_canonical.rtlil
```

Note the order: keep discovery *did* run and found the 16 modules, but
inside a build action, after the per-module canonicalization actions
would have had to be declared. The names arrive one phase too late, which
is the whole problem.

The 32 was kept so "the action graph for those twenty designs is exactly
what it was". That graph never completes, so what it preserves is a
failure.

### Fix (bazel-orfs)

When `SYNTH_HIERARCHICAL=1` and `keep_modules(arguments)` is empty, do
not set `SYNTH_NUM_PARTITIONS`. `private/rules.bzl` then reads 0 and takes
the **serial path**, which runs ORFS's own `synth.tcl`. That script
handles this case natively: `synth -run :fine`, then
`keep_hierarchy -min_cost $SYNTH_MINIMUM_KEEP_SIZE` (or plain
`keep_hierarchy`), then flatten the rest. It is exactly what `make`
does for these designs in ORFS, and it was the only path bazel-orfs had
before parallel synthesis landed in March 2026. Serial yosys is
deterministic, so the reproducibility argument for a static partition
count is unaffected.

The warning stays, reworded: parallel synthesis is unavailable without a
pinned list, so this design synthesizes serially; pin
`SYNTH_KEEP_MODULES` to parallelize. The capture recipe stays in the
message.

`test/keep_modules_test.bzl` is unaffected. A small analysis test pins
the new default: hierarchical with a list → `SYNTH_NUM_PARTITIONS` equals
the list length; hierarchical without → the variable is absent.

### Follow-up (ORFS, human decision)

Pin `SYNTH_KEEP_MODULES` in `asap7/coralnpu/config.mk` the way
`asap7/swerv_wrapper/config.mk` does, captured from the serial run's
`keep_hierarchy` output. coralnpu's rules file bounds it at ~200k
standard cells, so serial yosys will be slow and the list is worth
having. It is a follow-up, not the fix: the list drifts with each RTL
snapshot (#4474 is titled "snapshot"), and a design should build before
it builds fast. The same offer stands for aes-block, riscv32i and
microwatt; they are small enough that serial is fine.

## 5. C: swerv_wrapper's dropped `$(CLKGATE_MAP_FILE)`, benign

swerv lists `$(CLKGATE_MAP_FILE)` in VERILOG_FILES; the parser cannot
make a label from an unexpanded platform variable and drops it with a
warning. ORFS's `synth_preamble.tcl` reads `CLKGATE_MAP_FILE` itself, on
both the slang and the read_verilog paths, and the platform defines it,
so the model is present in every synthesis regardless. No bazel-orfs
action. An ORFS tidy, dropping the entry from swerv's config.mk, would
silence the warning; optional.

## 6. The guard that was missing

CI loads every @orfs design package with
`bazelisk query '@orfs//flow/designs/...:*'`. That catches DSL skew and
was deliberately not `build --nobuild`, because analysing *everything*
drags in ORFS's `gcd_single_flow_*` tests that reference `@openroad`.
But loading a package does not resolve the labels its rules reference,
which is exactly where problem A lives.

Add a step that analyses the flow targets only:

```sh
bazelisk build --nobuild --keep_going \
  $(bazelisk query 'filter("_route$", kind(rule, @orfs//flow/designs/...))')
```

Section 2 shows this at 28 s for 32 targets; all platforms should stay
under a couple of minutes. It would have failed on the day the pin moved
to an ORFS containing coralnpu.

## 7. Steps

Ordered so that each PR carries one concern and the coralnpu build the
plan started from is the acceptance test at the end.

1. **This document.**
2. **PR: generate `files()` BUILDs for src directories** (section 3)
   with the test changes and the doc paragraph. Acceptance:
   `bazelisk build --nobuild @orfs//flow/designs/asap7/coralnpu:CoreMiniAxi_route`
   analyses; the 32-target sweep stays green; unit tests pass.
3. **PR: CI analysis guard** (section 6). Could ride with step 2 as its
   regression test; kept separate so the CI change is reviewable on its
   own.
4. **PR: serial fallback for hierarchical designs without a list**
   (section 4). Acceptance:
   `bazelisk build @orfs//flow/designs/asap7/riscv32i:riscv_top_synth`
   completes, the smallest affected design. Then
   `asap7/coralnpu:CoreMiniAxi_synth`.
5. **Run `asap7/coralnpu:CoreMiniAxi_route`** to completion. This is the
   original request and the first time the design runs under bazel at
   all, so it may surface flow-level problems that are not wiring. Those
   get their own plan; they are not pre-judged here.
6. **ORFS follow-ups, on request:** pin `SYNTH_KEEP_MODULES` for coralnpu
   from step 5's synth log; optionally the swerv config tidy. Each is an
   ORFS PR followed by a `//:bump`, inside the 30-day window.

## 8. Not yet proven

- That the serial path completes for coralnpu in acceptable time. It
  completes for the design under `make` in ORFS CI, and the rules file
  was produced by such a run, so the tool side is known good; the
  question is only wall time under bazel's sandbox.
- That no other reference shape under the three platforms needs a
  package the src rule would not produce. The sweep says no at this pin.
  Step 3 is what keeps that true at the next one.
- Anything downstream of synth for coralnpu. Step 5 measures it.
