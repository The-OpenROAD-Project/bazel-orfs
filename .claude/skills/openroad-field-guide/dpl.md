# dpl: legalisation and detailed placement

Paths are in OpenROAD's `src/dpl/`, ORFS's `flow/scripts/`. dpl runs at
place and again inside every later repair (cts, grt, antenna repair)
through `detailed_placement_helper`.

## Reading the log

- The default engine is the **negotiation legaliser** (DPL-1102): phase 1
  up to 400 iterations, phase 2 up to 1,000, window +-20 sites x +-5 rows.
  Stuck for 3 iterations: falls back to diamond search (DPL-0700/0702).
  `diamond recovery: recovered k/n stuck cells` follows: a stage that
  passes with these lines needed a safety net, and has a cause.
- **DPL-0701 "did not fully converge. Violations remain: N" is only a
  warning.** The flow goes on; `check_placement` (FLW-12, DPL-0033)
  catches it later. DPL-0701 with no DPL-0700/0702 before it is phase 2
  reaching its 1,000 iterations with the count still moving, a path that
  ran no diamond recovery at all until OpenROAD #12233 (carried 0216,
  which also prints DPL-0704 there).
- **DPL-0703 (carried 0216) says why cells were left to the diamond
  search**, one line per cause, each naming its fix: started over fixed
  instances (and the hierarchy they share: keep placement out of it),
  no free run of their width in the window (the area is full: give it
  room, a wider window does not help), placed beyond the window (the
  `-site_search_window`/`-row_search_window` that would reach them), no
  site within `-max_displacement`. Read it before widening a window or
  switching to the diamond legaliser.
- Diamond mode (`-use_diamond_legalizer`, DPL-1101) fails hard:
  DPL-0034/0035/0036. DPL-0036 after resizer/CTS buffers land inside
  hard-block footprints: bazel-orfs #1188 moves them out first.
- DPL-0501 moves/displacement/HPWL delta; DPL-0500 runtime.

## Where the time goes

Single-threaded. It degrades when gpl leaves dense clumps, or when CTS
drops cells into channels.

- The negotiation legaliser was the parent's budget breaker after CTS:
  more than 2 h, 47 GB, hot in `negotiationCost` and `compare_by_id`
  (`ideas/xiangshan-timing.md` entry 5). Diamond search with a 100 um
  window passed in 80 min. Among many FIRM cells (a dissolved design) use
  the diamond legaliser.
- **No legalisation exists in the window** used to mean 82 min to 2+ h of
  diamond search before failing. Carried 0004 checks Hall's condition and
  fails in seconds (OpenROAD #12122 open).
- `initialSnap` grinds on cells far from rows: gpl stranded them, see
  [gpl.md](gpl.md) (carried 0086).
- **A register file's own flow** (ORFS 0172) places generate_ram's array
  FIRM, nearly full but for holes a few sites wide, and leaves global
  placement generate_ram's input buffers (`-periphery unplaced`), the
  port buffers and repair's buffers. gpl put them over the array and the
  negotiation legaliser stalled (DPL-0700 on test/regfile/band, 102 of 155
  cells over the array; on another register file it ran out of
  iterations and failed, DPL-0701/0033). Carried 0215 puts soft
  placement blockages over the array in strips that leave its free
  columns (generate_ram's service columns) open: phase 1 converges.
  Before it, XiangShan's register files were set to the diamond
  legaliser (`xiangshan.bzl`), which hid this.
- `improve_placement` (`ENABLE_DPO=1`): HPWL only, not timing-aware,
  single-threaded. `ENABLE_DPO=0` when slow.

## Where the memory goes

The **pixel grid**: one 48-byte `Pixel` per core site, ~32 GB on XSTile's
666 M sites. It used to stay resident after the command, through grt:
freed by OpenROAD #12120 (116.5 -> 94.3 GiB on XSTile Top). It is
rebuilt by each repair's legalisation.

## Levers

`DETAIL_PLACEMENT_ARGS` (`-max_displacement`, `-site_search_window`,
`-row_search_window`, `-use_diamond_legalizer`; applies to every
re-legalisation), `CELL_PAD_IN_SITES_DETAIL_PLACEMENT`, `ENABLE_DPO`,
`DPO_MAX_DISPLACEMENT`. DPO variables are place-scoped since ORFS #4616;
before that a deployed floorplan tree ran later stages on platform
defaults.
