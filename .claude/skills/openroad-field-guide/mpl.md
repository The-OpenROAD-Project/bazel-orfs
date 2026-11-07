# mpl: macro placement (Hier-RTLMP, `rtl_macro_placer`)

Paths are in OpenROAD's `src/mpl/`, ORFS's `flow/scripts/`.

## Reading the log

`HierRTLMP::run`: multilevel clustering on the logical hierarchy (large
flat clusters split by TritonPart), coarse shaping, top-down simulated
annealing over a sequence pair at each level, hard-macro annealing
inside macro clusters, the Pusher, orientation fixes.

- Info level shows only the clustering table and the placement
  summaries. **Annealing progress is not logged**:
  `set_debug_level MPL hierarchical_macro_placement 1`.
- Failures: MPL-0055 utilisation relaxed (warn), MPL-0040 no solution at
  any std-cell density, **MPL-0008 annealer found nothing valid**,
  MPL-0003 no valid tilings for a mixed cluster, MPL-0004 does not fit
  the outline, MPL-0016/0065 area with halos exceeds the floorplan,
  MPL-0017 every macro fixed, placer skipped.

## Where the time goes

- **No early stop**: always 2,000 steps x max(#macros, 500) moves, each
  re-packing the sequence pair (O(N^2) in blocks). Runtime explodes with
  the number of blocks in one cluster (hundreds of macros in a parent).
- 10 runs, in batches of min(10, threads): **more than 10 threads does
  not help.** Step and run counts are compile-time constants; no Tcl knob
  shortens the annealing.

## Levers

`RTLMP_MAX_LEVEL`, `RTLMP_MAX/MIN_INST`, `RTLMP_MAX/MIN_MACRO`,
`RTLMP_MIN_CHANNEL_SIZE` (replaces the deprecated halos; channel = 2 x
halo), `RTLMP_PIN_AWARE_CHANNELS`, the `RTLMP_*_WT` weights, `RTLMP_ARGS`
(replaces everything else), and **`MACRO_PLACEMENT_TCL`, the real escape
hatch**.

## Futile, or nothing there

- **`RTLMP_MAX_LEVEL` is silently forced to 1** when any macro is fixed,
  or when the INST/MACRO thresholds are unset and there are fewer than 15
  macro masters (`clusterEngine.cpp`).
- Per-retry seeds do not rescue an MPL-0008 whose parent handed a child a
  zero-slack outline (OpenROAD #11628).
- RTL-MP's objective predicts area, not period: once memories are timed
  it does not beat bazel-orfs's own annealer on CoupledL2 (3,330 vs
  3,328 ps at the parent, bazel-orfs #1177). Noise is born at macro
  placement (#867).
- An exact CP-SAT packing check plus annealing early stop (OpenROAD
  #11807-#11809 drafts, bazel-orfs #1290): no slower, legal placements in
  30 of 771 annealing failures, but no DSE time saved. Closed as
  experiments, patches dropped. **Dead end.**
- The E12 clustered global-place scorer: "the readout is the limit, not
  the clustering" (`ideas/e12-clustered-scorer.md`). **Dead end.**

## Known problems

- A second `rtl_macro_placer` in one process segfaulted: fixed, OpenROAD
  #11625. ORFS still runs the placer when `MACRO_PLACEMENT_TCL` fixed
  every macro, then trips on FIRM std cells: carried 0083.
- The Snapper snaps SIGNAL pins only: a macro whose only M2 pin is its
  clock sits 2 nm off-track and drt stops on DRT-0073. Carried 0177.
- MPL-0045 (flat cluster of one macro plus a few thousand cells, OpenROAD
  #11820) and MPL-0005 (orientation mirrors a macro off the track grid,
  #11819) are open.
- No `-random_seed` to draw candidate placements (OpenROAD #11315
  closed); `-write_macro_placement` output rejected by `place_macro`
  (#11278 closed).
- A fail-early feasibility check (`check_macro_placement`, OpenROAD
  #11496) was closed for false positives: std-cell area shrinks later
  (`remove_buffers`, `replace_arith`). Any early check must be a lower
  bound.
- Facing SRAM pin edges across a 4 um channel forces unbuffered wires;
  12 um took CoupledL2 1,982 -> 1,437 ps (bazel-orfs #1251).
