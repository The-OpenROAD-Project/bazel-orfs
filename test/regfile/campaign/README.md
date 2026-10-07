# riscv32i register-file campaign

The gate: riscv32i-regfile to global route at or below riscv32i's
flip-flop minimum period (954 ps at a 950 ps clock), area reported.
`results.md` is every measurement so far.

## What is where

- `patches/0010-openroad-ram-generate-regfile.patch`: the generator.
  `predecode.diff` and `word-groups.diff` are variants of its
  `src/ram/src/regfile.{cpp,h}` against the generator at e5dcafd8.
- `patches/0089-orfs-auto-memories-regfiles.patch`: the ORFS side; the
  riscv32i spec and config are `flow/designs/asap7/riscv32i-regfile/`.
- `//test/regfile:riscv32i_{flops,regfile}_<stage>_odb_debug`: an
  odb-debug session on each stage, for `measure.sh` and for questions.

## One measurement (about 10 minutes, under 1 GB)

    test/regfile/campaign/set_spec.py 1 45      # bit_folds, utilisation or -
    test/regfile/campaign/measure.sh "flat, 45 %"

## Generator variants

Apply a diff to `src/ram/src/regfile.{cpp,h}` as extracted from patch
0010 and fold them back into the patch's new-file hunks (each is a
whole-file hunk `@@ -0,0 +1,N @@`), then `bazelisk build
@openroad//:openroad`. A change to the read or write structure moves the
goldens in `src/ram/test`: `OPENROAD_SRC=<OpenROAD checkout>
test/regfile/campaign/golden.py <openroad binary>` regenerates them;
`//test/structured_gen_lec:all_lec_tests` checks equivalence.
`gate.sh <openroad>` compares array shapes in seconds without a flow.

## In parallel

Every lane needs its own worktree: a deps tree and `measure.sh` build
from the patches as they are in that checkout, and a second lane that
edits them changes what the first one installs mid-run. One worktree per
generator or spec variant, each with its own Bazel output base; the
remote cache makes the second and later ones cheap.

## Measured 2026-10-07, see results.md

The write clock gate (`write_style clock_gate`, patch 0010) and inlining
(`AUTO_MEMORIES_MACRO_PLACE`, ORFS patch 0091) put riscv32i-regfile at
parity with the flops, 955 against 954 ps, on a 12 % smaller core. The
clock-period campaign after it (predecode, a mux-tree read, wider and
stronger read trees) found nothing past the noise; results.md has each
arm and why.

`never_macro.sh` was the hand-swapped prototype of inlining, kept for
the record; the flow does it now. `clock_cost.tcl` and `hold_cells.tcl`
are the clock gate's cost side.

## Later

Global route with `-congestion_iterations 0 -allow_congestion` for the
riscv32i and riscv32i-regfile measurements, as XiangShan routes: only
the minimum period and the turnaround matter here. Check the period is
unchanged within noise and record the stage time before and after.
