# `fork` — a fork/join snapshot idiom for run scripts

## Why

Configuration studies walk a *tree* of flow decisions (placement flavor ×
routing iterations × repair effort × ...). Run as independent processes,
every configuration re-pays the shared prefix — load, floorplan, placement —
even when it differs from its sibling only in the last stage. POSIX `fork()`
turns the running process into a copy-on-write snapshot: a child continues
down one branch while the suspended parent holds the pre-branch state for
free, so every tree *edge* is computed exactly once instead of once per leaf.

Fork here is a **snapshot mechanism, not parallelism**: the default walk is
depth-first with exactly one active child at a time, so the machine's CPUs
and memory always belong to a single run. Suspended ancestors are frozen in
`waitpid` and cost only the pages the active child has diverged. It is an
in-memory `write_db`/`read_db` checkpoint that costs nothing to take and
nothing to resume.

## The idiom

Any `orfs_run` / `orfs_run_executable` script may:

```tcl
source $::env(ORFS_FORK_TCL)

fork gp_mode {plain timing_driven} {
    run_global_placement $gp_mode
    fork grt_iters {0 2 5} {
        run_global_route $grt_iters
        write_leaf_json $::env(RUN_OUTPUT_DIR)/${gp_mode}_${grt_iters}.json
    }
}
```

`fork ?-parallel? ?-jobs N? ?-timeout seconds? varName valueList body` forks one
copy-on-write child per value; the child sets `varName` in the caller's
scope, evals `body` there, and `_exit`s. The join is implicit: `fork`
returns once every child is reaped, with a dict mapping each value to its
exit status — `0` ok, `1` a Tcl error in the body, `N` an explicit
`::orfs::posix_exit N`, `128+SIG` a crash (`142` = SIGALRM: the child ran
past `-timeout` and self-destructed). A failed child never stops the
walk: its status is recorded and the remaining siblings still run, so a
crashed or runaway branch loses only its subtree. `-timeout` is enforced
*inside* each child via `alarm(2)` — a parent-side kill would orphan the
child's own running descendants, which then hold the machine and the
stdout pipe open; deadlines do not survive fork, so nested forks pass
their own `-timeout`. `-parallel` forks all children before joining —
shared edges are still paid once, but siblings contend for the machine,
so use it only when nothing downstream reads runtimes.

**`-parallel` is unbounded, and that is a guarantee rather than an
oversight**: every child is alive at once, so a body may rendezvous
across siblings. The cost is that a wide value list oversubscribes the
machine — a 41-leaf wave put 41 OpenROAD processes on 16 cores, which
does not make the walk faster and does make its runtimes meaningless.

**`-jobs N` is the option for a wide fan-out.** It keeps at most `N`
children alive, forking the next only as one is reaped — a bounded worker
pool, the way a build tool schedules. `-jobs default` takes the count
from `ORFS_FORK_JOBS`, else `nproc`, which honours CPU affinity so a
`taskset`- or cgroup-confined run gets what it is actually allowed. Since
`fork` has already quiesced the host to a single thread, one child per
core is one tool process per core.

The two are mutually exclusive and `fork` rejects both together, because
they promise opposite things: **under `-jobs` a body must never wait on a
sibling**, which may not have been forked yet. That deadlocks; rendezvous
needs `-parallel`.

Reaping is oldest-first, because `waitpid` takes a specific pid — a child
that finishes early is not reaped until those ahead of it are. That costs
a little throughput when durations vary and keeps the bound exact, which
is the property worth having.

Raw primitives (`::orfs::posix_fork`, `::orfs::posix_waitpid`,
`::orfs::posix_exit`) live in `//fork:liborfsfork.so`, a Tcl-stubs
extension `load`ed by `fork.tcl` from `$ORFS_FORK_LIB`. Both env vars are
provided automatically by `orfs_run` and `orfs_run_executable`. The
extension is compiled against the same `@tcl_lang` the openroad module
embeds, so it can never drift from the interpreter that loads it.

## Where results go

Pair the walk with an output folder — each leaf writes one independent
file, results are incremental, and a crashed subtree leaves the other
leaves' files intact:

- `orfs_run(out_dir = "...")` declares a directory output and exports its
  path as `$RUN_OUTPUT_DIR`.
- `orfs_run_executable` callers pass an absolute scratch path per
  invocation (e.g. `RESULTS_OUT=/abs/scratch/...`), like `LOG_DIR`.

## Fork hazards (read before writing a walk)

- **A child cannot raise its own thread count.** `fork` quiesces the host
  to one thread before forking, and it is tempting to think that makes it
  safe for a child to raise the count again — it does not.
  `//test:fork_smoke` probes exactly this: the child wedges in
  `futex_do_wait` with a single thread while the parent sits in
  `do_wait`, indefinitely. The probe carries a `-timeout` so it reports
  status 142 instead of hanging the suite.

  This sets a scheduling rule, since every ensemble member is therefore
  single-threaded. When the fan-out is at least the core count that is
  the fastest arrangement anyway — tool thread-scaling is sublinear while
  process parallelism is not. When the fan-out is *smaller* than the core
  count, `fork` leaves the machine idle and nothing inside the walk can
  spend the rest, so separate processes are the better tool. And `fork`
  only earns its keep through the shared prefix: configurations diverging
  at a late stage share nearly everything, while an ensemble that
  perturbs the floorplan diverges at the root and shares only the design
  load — ~9s of a ~470s leaf on `multiplier_top`. Measure the prefix
  before reaching for `fork`.

- **Threads do not survive fork**: only the forking thread exists in the
  child. OpenSTA/OpenROAD respawn their worker pools on demand (validated
  by `//test:fork_smoke`, which runs timing queries in forked
  grandchildren), but if a tool hangs in a child right after a fork,
  re-issue its thread-count command (e.g. `set_thread_count`) at the top of
  the body.
- **No event-loop code in bodies**: `vwait` / `after`-driven callbacks
  inherited from the parent will not fire correctly in a child.
- **stdio**: the extension `fflush(NULL)`s before forking and children
  leave via `_exit`, so output is not duplicated and the host's exit hooks
  run only in the root process. With the sequential default, children's
  log output interleaves in order; under `-parallel` it interleaves
  arbitrarily.
- **Linux only**: fork-without-exec is unsafe on macOS hosts;
  `//fork:liborfsfork.so` is restricted to Linux.

## Tests

- `//fork:fork_test` — the idiom's semantics in hermetic tclsh
  (sequencing, statuses, crash tolerance, nesting, `-parallel` barrier,
  the `-jobs` bound, and that the two are rejected together).
- `//test:run_out_dir_test` — `out_dir` / `$RUN_OUTPUT_DIR` end to end
  (fast, mock-openroad).
- `//test:fork_smoke_test` (manual) — the walk inside real OpenROAD after
  `load_design`, timing queries in forked children, one JSON per leaf in
  `$RUN_OUTPUT_DIR`, a deliberate failing leaf.
