# scale-to-memory

`orfs_schedule()` (docs/schedule.md) packs a design's macro flows into
waves that fit free memory and runs the parent alone, last. It reads
`resources.json` beside the design's `BUILD` file. You write the first
one; runs measure and refresh it.

## No resources.json: write it, in minutes

The runner stops without one. Do not run a serial measuring build to
make it: assess.

1. **Qualitative (seconds).** Read the `orfs_schedule()` call and the
   flows it names. Which units are macros, which the parent, what nests
   (a register-file macro is built before the block that reads it: list
   it as its own schedule or build it first), what is already cached
   (`cache-miss` skill: a cached unit costs nothing to "build").
2. **Quantitative (minutes).** Get each unit's instance count from the
   cheapest artifact that exists: the synthesis report
   (`reports/<platform>/<unit>/<variant>/synth_stat.txt`, the cell
   count) or a floorplan's instance count. Build `<unit>_synth` if
   nothing is cached; synthesis is the cheapest stage. Multiply by the
   factors below, per stage.
3. **Write** each entry with `"source": "estimated"` and a `basis`
   ("1.1 M cells x 33 kB at grt"), the commit and the date.
4. **Show** `bazelisk run //<pkg>:build -- --plan-only` and check the
   waves make sense before building.

### Per-instance factors (asap7, ORFS defaults)

Calibrated on XiangShan's XSTile parent (about 3.6 M instances, 2026-10):

| stage | peak memory per instance | wall time |
|---|---|---|
| synth | (partitioned: the largest partition) | 20-40 min per M cells |
| floorplan | ~2.5 kB | ~25 min per M instances |
| place | ~8 kB | 0.5-2 h per M instances (timing-driven placement is the long tail) |
| cts | ~23 kB | ~25 min per M instances |
| grt (route-0, repair) | ~33 kB | 15-60 min per M instances, repair-bound |

A quicker proxy when stage databases already exist: about 20 GB of peak
per GB of the stage's `.odb` (XSTile's grt, Frontend's CTS). It
underestimates small blocks: FltRegionModule's placement took 10 GB
against 6 estimated from its 0.3 GB db; pad blocks under 1 GB by 2x.

These come from one large parent. Blocks of a few hundred thousand
instances fit them loosely: Frontend's CTS peaked at 20 GB. When a
`:build` run measures a block, replace the estimate (the run does it) and
correct this table when a measurement is more than 30 % off a factor.

## Run

```sh
bazelisk shutdown
systemd-run --user --scope -q -p MemoryMax=<budget>G -p MemorySwapMax=64G \
  bazelisk run //<pkg>:build
```

- `bazelisk shutdown` first: the actions run in the Bazel server, and a
  server keeps the cgroup it was started in. One started earlier,
  outside the scope, builds uncapped.

- The scope keeps the build to the budget; swap lets an underestimate
  page instead of the kernel killing it. After the run, check
  `journalctl -k | grep "Killed process"`.
- One parent at a time, ever, and nothing heavy beside it.
- Stop a runaway job by its recorded PID, never by a pattern
  (`pgrep -f` matches your own shell).
- A deps-lane run (`deps-lane` skill) is outside the scheduler: it holds
  memory the budget does not see. Lower `--budget` while one runs.

## After a run

The run prints `resources.json updated for [...]` when a unit was
estimated or measured more than 20 % off. Commit it with the change that
moved it, or on its own when it is materially out of date: a new unit, a
new stage, a peak that moved. A run that paged says the record is low:
rerun with a lower `--budget`.
