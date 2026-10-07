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

## Lined up, not run

| experiment | how | expected |
|---|---|---|
| predecode | `predecode.diff`, flat 45 % | one serial AND2 less on the select path, ~10-20 ps |
| dissolve, then unplace | `unplace.tcl` on `2_floorplan.odb` in a `//:deps` tree at place, then place, cts, grt | does free placement of the better netlist beat 1003 ps at 62 %? |
| never a macro | riscv32i's `//:deps` tree at synth with `src/riscv32i/regfile.v` replaced by the generated `memories/regfile.v`; core from the real cell area at 62 % | the floorplan without a macro's tiling constraint |
| shape annealer | at floorplan, before macro placement: the generator's shapes per register file (ports unchanged), the FakeRAMs, channels and the real standard-cell area; the chosen shape generated there, the instance moved to it with `swapMaster`; `mode netlist` only | the shape that fits the smallest core; the 62 % flat run shows a shape must also weigh select-line length |
| write side | a clock gate per word in place of the per-bit AO22 hold mux, as `generate_ram` does | ~20 ps off every endpoint, narrower tiles; changes CTS |
