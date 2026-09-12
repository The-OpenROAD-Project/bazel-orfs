# What this study cost to run

Kept while the campaign ran, not reconstructed afterwards. Every entry is
something that actually happened, including the dead ends: an intervention
count that flatters the method would be worth nothing.

Machine: a shared workstation, not idle for the whole campaign -- a second
checkout of this repo was building throughout the setup phase (1-minute load
average 17.7 at the time the first rung was submitted). Threshold results are
booleans and survive that; wall-clock numbers taken under load are marked in
the samples via `loadavg_at_start` and are not quoted as timings.

| when (UTC) | what happened | cost |
| --- | --- | --- |
| 2026-09-12 08:23 | campaign started, worktree branched from main | -- |
| 2026-09-12 08:26 | `bazelisk run //:bump -- --head openroad` refused: it moves the whole stack, and ORFS master no longer takes `patches/0037-orfs-single-writer-1_synth-sdc.patch`. Bumped openroad alone through the bumper's own `update_openroad_archive_override()` instead of rebasing a patch this study does not need. | ~10 min |
| 2026-09-12 08:40 | baseline openroad (master, unpatched) built: 845 s wall, 5562 of 8840 actions from the remote cache. | 14 min |
| 2026-09-12 08:55 | PR #11395 applied cleanly to master; patched binary built in 61 s (gpl objects only). Witnessed both ways: `info commands estimate_target_density` names the command with the patch and prints nothing without it. | 1 min |
| 2026-09-12 09:05 | first harness attempt failed analysis twice -- `str.rjust` does not exist in Starlark, and mock-alu/mock-cpu carry design-private variables that `orfs_flow`'s spell-check rejects until they are routed through `user_arguments`/`user_sources`. | ~15 min |
| 2026-09-12 09:20 | first rung submitted (`gcd_t08_place`). | -- |
| 2026-09-12 09:36 | it failed after 16 minutes with `ORD-0007 ... 2_floorplan.odb does not exist` -- the trap `test/pre_route_pessimism/stage_src.tcl` documents: ORFS derives `RESULTS_DIR` from the package that *declares* the run, so a place stage declared here cannot start from a floorplan built in the design's own package. Restructured so each design's synth+floorplan is declared here once and shared by every rung through `previous_stage`. | 16 min of machine time, ~20 min of work |
| 2026-09-12 09:40 | while the rebuild ran: checked whether the flow can even reach the `doIncrementalPlace` hunk the PR deletes. ORFS calls `global_placement -incremental` in exactly one place (`resize.tcl`), gated on `SWAP_ARITH_OPERATORS`. In the asap7 set that is on for **mock-alu, riscv32i and ibex** and off for everything else -- so the A/B is worth running on two designs of the eight, and the rest would have measured nothing. | saved ~6 place-stage pairs |
| 2026-09-12 09:45 | restarted the rung with `--//:log_timestamps` after starting it without: the flag is part of the cache key for every flow action, so mixing it across arms would have meant re-running them. | ~2 min |
| 2026-09-12 10:05 | first rung landed. Two harness bugs it exposed, both of the silent kind: every rung wrote to `results/asap7/<design>/base/`, because ORFS keys that path on the flow variant and not on the target name (two rungs would have overwritten each other), and the log discovery found each log twice, once in the `.runfiles` copy. | ~20 min |
| 2026-09-12 10:20 | gcd's ladder came back "hit at every rung", which says the threshold is at or below the bottom of the ladder rather than saying where it is. Added the two arms that answer the question a maintainer would actually ask -- the design as shipped, and the same design with the estimate driving the density -- and read gpl's own first-iteration overflow as the check on the estimate's arithmetic. | ~25 min |
| 2026-09-12 10:35 | reading the first real log turned up **GPL-0186** ("Binary search didn't converge after 20 iterations") on gcd. The harvester was quoting a number gpl had already disowned; it now attributes the warning to the estimate it precedes, and the table prints it. | ~15 min |
| 2026-09-12 10:40 | full sweep started over the eight designs. | 3 h 10 min of machine time |
| 2026-09-12 13:50 | sweep finished, seven of eight designs measured. jpeg failed in synthesis: `dct_cos_table.v: No such file or directory`. Its `VERILOG_INCLUDE_DIRS` is a directory, so nothing in `sources` stages it, and the path itself is ORFS-repo-relative and only resolves inside @orfs's own packages. Fixed both halves -- re-root such paths, and depend on the `:include` filegroup the way ORFS's own design DSL does. | ~30 min |
| 2026-09-12 13:55 | re-ran the whole sweep so every sample carries the schema the parser grew during the day (ORFS's metrics JSON, the GPL-0186 flag, the buffer churn between probe and placer). Seven designs replayed from cache in about four minutes; only jpeg had to be built. | 4 min + jpeg |
| 2026-09-12 14:05 | a background waiter was killed by the kernel for memory; the campaign itself survived. The machine has 30 GB and was also hosting another checkout's builds for the first two hours -- recorded because it is the reason no wall-clock number from this campaign is quoted as a timing. | none |
