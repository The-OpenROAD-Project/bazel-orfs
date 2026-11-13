# gpl: global placement (RePlAce / ePlace Nesterov)

Paths are in OpenROAD's `src/gpl/`, ORFS's `flow/scripts/`.

## Reading the log

Initial placement (conjugate-gradient B2B, up to 20 rounds,
`[InitialPlace] Iter`), then the Nesterov loop: wirelength gradient plus
an FFT electrostatic density gradient, the density penalty ramping each
iteration, until overflow <= 0.1.

- Table `Iteration | Overflow | HPWL | Penalty`, a row every 10
  iterations. **Healthy: overflow falls monotonically from ~1.0 to 0.10**,
  penalty grows geometrically, HPWL rises gently.
- GPL-1001 finished; GPL-1010 hit 5,000 iterations then GPL-0121 reverted
  to the min-HPWL snapshot. GPL-0323/0324/0998/0997 divergence, GPL-0304
  diverged at iteration 1 (lower `-init_density_penalty`).
- **Cells trapped in a wide blockage**: overflow stuck near 0.92 from
  iteration 10 and creeping to 0.997, penalty to 1e33, then GPL-0305.
  The nets pull the cells into a blocked region (a register file's FIRM
  array under 0215's strips); inside it the density force is flat and
  free columns a few sites wide next to it are out of reach. Finer bins
  (`-bin_grid_count 512`) and a spread start do not help. Leave such an
  array unblocked (0215 does when the band cannot hold the cells, on
  XiangShan's FpRegFile/VfRegFile). Without IOs and with only
  high-fanout nets, initial placement also piles every cell in the
  core's corner (fixed upstream, OpenROAD #12232, after our pin).
- **Timing-driven events**: GPL-0100 "Timing-driven iteration i/N,
  virtual: ...", GPL-0106 worst slack, GPL-0107-0109 repair_design area
  and gcells, GPL-1013 total. GPL-0105/0102 "no slacks found.
  Timing-driven mode disabled" is nearly always an SDC problem.
- **Routability**: GPL-0038 snapshot at overflow 0.6, GPL-0040 RUDY
  congestion at 0.3 vs target 1.01, GPL-0086 inflate, **GPL-0087 revert
  to the 0.6 snapshot and run again**. Stops on GPL-0090 target reached,
  GPL-0054 no improvement 3x, GPL-0097 inflation budget (30 % of movable
  area), GPL-0091 50 reverts, GPL-0089.
- **Grind signature**: repeated GPL-0087/GPL-0040 with flat congestion.
  Fix the floorplan or density; waiting does not help.

## Where the time goes

**Not in the Nesterov kernels on a real design.** Measured on
FltRegionModule (bazel-orfs record of OpenROAD #12032): a 4.15x Nesterov
speedup gave 1.03x on `global_placement`; timing-driven `repair_design`
and routability dominate.

- **Timing-driven: two events per run** (overflow 64 % and 20 %). Each
  calls `Resizer::findResizeSlacks`: a full `estimate_parasitics`, a full
  `repair_design`, `fullyRebuffer()` over every non-buffer driver, and a
  slack sweep. With ORFS defaults (`GPL_KEEP_OVERFLOW` unset) **both
  events keep their buffers**, not only the last.
- **Routability**: each revert re-runs the 0.6 -> 0.3 stretch.
- **`3_1_place_gp_skip_io` is a second full Nesterov run** (no IOs, no
  driven modes) to feed ppl. Skipped when pins are fixed in floorplan or
  with `GPL_PLACE_IOS=1`; one `-place_ios` placement instead of three
  steps took place from 9:02 to 5:17 on wirebound (bazel-orfs #1052).
- **SMT oversubscription**: gpl runs one thread per physical core
  (OpenROAD #11368) with passive OpenMP waits (#11346).

## Where the memory goes

GCell/GPin/GNet copies of the netlist, fillers, the bin grid and FFT
arrays; ~8 GB for 4 M instances. Timing-driven adds the STA graph and
parasitics: on big designs the driven callbacks, not gpl's own data, set
the peak (bazel-orfs #1153 notes).

## Levers

| ORFS variable | Effect |
|---|---|
| `PLACE_DENSITY`, `PLACE_DENSITY_LB_ADDON` | `-density`; lower spreads cells, eases congestion, costs wire |
| `GPL_TIMING_DRIVEN` (1) | 0 drops both repair_design events: biggest runtime lever, **large period cost** (below) |
| `GPL_ROUTABILITY_DRIVEN` (1) | 0 drops the revert loop |
| `GPL_KEEP_OVERFLOW` | keep resizer changes only below this overflow |
| `MIN/MAX_PLACE_STEP_COEF` | fewer iterations vs divergence risk |
| `GLOBAL_PLACEMENT_ARGS` | `-timing_driven_net_reweight_overflow`, `-routability_*`, `-overflow` |

## Futile, or nothing there

- Initial cell positions: worth 0.40x the seed's own noise to the
  finished design (bazel-orfs #985).
- `estimate_target_density` reports back the density it was handed
  (bazel-orfs #980).
- Raising `routability_max_density`: cannot create space. Cell area /
  free area (GPL-1004) is the density floor.
- SIMD wirelength, density OpenMP modernising, pin-count memo: measured
  on a 700k-instance design and withdrawn (OpenROAD #11071-#11086).

## History

- **Timing- and routability-driven placement off "for turnaround" cost
  more than it saved**: on Frontend, turning them back on took place-stage
  period 5,118 -> 2,266 ps for 2x place time (bazel-orfs #1128, #1139).
- **Kept repair_design from the first timing-driven event** put 78
  repeaters on the parent's worst paths; dropping it took 5,402 ->
  4,226 ps (bazel-orfs #1143, `ideas/xiangshan-timing.md` entry 40).
- repair_design inside timing-driven gpl can diverge (+187k buffers):
  OpenROAD #11066 merged (stop doomed passes); removing the 5k buffer
  limit, #11151, closed.
- **gpl ignores rows**: cells land in bands with no rows and dpl then
  grinds forever (25 min in `initialSnap`, entry 21). Carried 0086 fails
  the gpl stage naming the stranded cells; the planner adds a placement
  blockage. Not upstreamed.
- Cluster pull (OpenROAD #11768 draft, bazel-orfs #1339): mixed on ORFS
  designs. **Dead end so far.** `placement_cluster` ignored by fillers and
  pin counts: OpenROAD #11316 closed.
- Parent density: 0.8 helps MemBlock (1,815 -> 1,696 ps, bazel-orfs
  #1253); mocking blocks to 0.6 was negative (#1164).
