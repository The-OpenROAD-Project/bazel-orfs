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

Predecode (negative), dissolve then unplace (no gain), never a macro,
and the write clock gate (`write-gate.diff`, a `write_style clock_gate`
spec key; patch 0010 carries it and riscv32i-regfile's spec uses it at
45 %). Never a macro with the write clock gate is at parity with the
flip-flops on a 12 % smaller core.

`never_macro.sh <lane>` runs riscv32i with the generated netlist in
place of `regfile.v`, in a `//:deps` tree.

## Lined up, not run

| experiment | how | expected |
|---|---|---|
| never a macro as a flow mode | the memories step hands synthesis the generated netlist in place of the module, no macro, no dissolve | what `never_macro.sh` measures, from the flow |
| shape annealer | at floorplan, before macro placement: the generator's shapes per register file (ports unchanged), the FakeRAMs, channels and the real standard-cell area; the chosen shape generated there, the instance moved to it with `swapMaster`; `mode netlist` only | only if the macro shape is kept: never a macro needs no shape |
| clock-gated write, CTS and hold | hold slack, clock power and the clock tree's buffers with 31 gated clocks against the flops' one | the cost side of the clock gate, not measured |
