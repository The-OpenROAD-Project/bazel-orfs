# rsz: repair_design, repair_timing, repair_hold

Paths are in OpenROAD's `src/rsz/`, `src/est/`, ORFS's `flow/scripts/`.
The `repair-timing-grt` skill covers measuring grt-stage repair;
`repair-headroom` covers what is left on the table. This file is where
the time goes and what does not work.

## Where repair_timing runs in ORFS

- floorplan: `-setup -sequence unbuffer,sizeup,swap,vt_swap`, zero wire,
  `TNS_END_PERCENT` still 100 % (`SKIP_FLOORPLAN_REPAIR_TIMING`).
- place: only with `ENABLE_PLACE_REPAIR_TIMING=1`; inside timing-driven
  gpl, `repair_design` runs twice ([gpl.md](gpl.md)).
- cts: setup **and** hold, placement parasitics (`SKIP_CTS_REPAIR_TIMING`).
- grt: setup and hold (`SKIP_INCREMENTAL_REPAIR`), then `OPT_POST_GRT_WNS`
  runs `-sequence "vt_swap reroute" -repair_tns 0`.

## Reading the log

- RSZ-0094/0099 "Repairing N out of M violating endpoints", then
  `Iter | Removed | Resized | Inserted | Cloned | Pin | Area | WNS | TNS |
  Viol | Worst`, a row every 10 iterations with `-verbose`.
- **Grind signature**: Iter climbs, WNS flat, Viol falls by ones, Area
  creeps. XSTile parent: WNS stuck at -835.6 ps from iteration 1,610 to
  1,990, at ~1,200 iterations an hour.
- RSZ-0062 unable to repair all setup; RSZ-0170 a slew no repeater can
  fix (driver R x repeater C floor); RSZ-0066/0064 hold buffers refused
  for setup.
- A huge hold count at CTS is a clock or SDC problem, not repair work.

## Where the time goes

**Measured (bazel-orfs #978): setup repair is 51-63 % of
floorplan+cts+grt wall time; the moves themselves 1-5 %. The rest is the
STA update (40-67 %), incremental grt parasitics (22-34 %) and, before
OpenROAD #11387, printing `-verbose` rows (88 % of a coralnpu floorplan).**

- The LEGACY loop works endpoints worst first,
  `#violating x TNS_END_PERCENT` of them (default 100 %), up to 10,000
  passes each, one move per pass, then incremental RC and `findRequireds`.
  Single-threaded.
- **Global stop** is checked every 100 iterations after iteration 1,000:
  TNS improved by < 0.01 % of the initial TNS (doubling each 1,000).
  Many slowly improving endpoints grind for a long time by design.
- **At grt, every `updateParasitics` first runs incremental FastRoute** on
  the touched nets: grt-stage repair is much slower per move than at cts.
  XSTile parent: setup repair at grt took 3,276 -> 2,406 ps but grt 19 ->
  84 min and 83 -> 102 GB (bazel-orfs #1212).
- OpenSTA exception `-to` lookups were 17-22 % of `repair_timing` on one
  design (OpenROAD #11933; carried 0145).
- `repair_design` on a flat 8 M-cell core did not return in 6.5 h; per
  block it takes minutes. Hierarchy is a runtime lever
  (`ideas/xiangshan-timing.md` entry 4).

## Levers

| ORFS variable | Effect |
|---|---|
| `TNS_END_PERCENT` | biggest runtime lever; WNS is always repaired. 100 -> 0 cost 0.17 ps, saved 135 of 270 s of grt (bazel-orfs #958) |
| `REPAIR_TIMING_PATH_GROUP` (carried 0179) | repair only reg2reg; stops repair chasing a block pin at -5.4 ns while reg2reg moves 2 ps (3,768 -> 2,826 ps) |
| `REPAIR_TIMING_MAX_ITERATIONS` (carried 0180) | caps the grind |
| `SETUP/HOLD_SLACK_MARGIN`, `SETUP_MOVE_SEQUENCE`, `SKIP_*` moves | per-move control |
| `SKIP_CTS_REPAIR_TIMING` | dropping it on the parent gained 4,226 -> 3,785 ps (bazel-orfs #1144) |

## Futile, or nothing there

- Repairing an endpoint whose one-flop-loop or wire floor is below the
  period (`repair-headroom`). Harder repair_timing finds 0.6-2.3 %.
- **Stopping rules**: no trajectory-reading rule dominates the default,
  knobs are Pareto trades (bazel-orfs #982, #987); `-effort` levels
  (OpenROAD #10900/#10942) closed "needs more data".
- Global-route parasitics are ~90x more accurate than placement ones but
  rank endpoints no better (bazel-orfs #1020).
- VT swap after CTS: block 22 % faster, tile 4 % slower because the
  boundary arc grew (bazel-orfs #1100). Use all VTs from synthesis.
- Deriving port limits from internal wire: limits no cell can meet
  (RSZ-0090/0169, bazel-orfs #1104). **Dead end.**
- Gotcha for VT experiments: OpenSTA `replace_cell` drops the reduced
  parasitics of driving nets; re-estimate or numbers come out ~2x too
  good.

## Known problems

- `repair_design` fixes long wires only with `-max_wire_length`, which
  ORFS never passes. Ports without design-rule limits gave 2.4 mm bare
  wires (fixed, parallaxsw/OpenSTA #518).
- `repair_design` hitting a dont_touch load inside a generated array
  (RSZ-3006): mark the array's internal nets dont_touch.
- Early sizing took a top-level port's modnet: crash, fixed OpenROAD
  #11590.
- `est` skips non-flat nets in incremental placement updates (TODO in
  `EstimateParasitics.cpp`); effect on `-hier` netlists unmeasured.
