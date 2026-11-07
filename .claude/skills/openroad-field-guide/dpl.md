# dpl: legalisation and detailed placement

Paths are in OpenROAD's `src/dpl/`, ORFS's `flow/scripts/`. dpl runs at
place and again inside every later repair (cts, grt, antenna repair)
through `detailed_placement_helper`.

## Reading the log

- The default engine is the **negotiation legaliser** (DPL-1102): phase 1
  up to 400 iterations, phase 2 up to 1,000, window +-20 sites x +-5 rows.
  Stuck for 3 iterations: falls back to diamond search (DPL-0700/0702).
- **DPL-0701 "did not fully converge. Violations remain: N" is only a
  warning.** The flow goes on; `check_placement` (FLW-12, DPL-0033)
  catches it later.
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
