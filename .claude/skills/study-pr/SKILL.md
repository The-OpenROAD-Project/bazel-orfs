---
name: study-pr
description: Run a measurement study on the flow and publish it as a closed, reference-only bazel-orfs pull request. Covers the two kinds of patch a study carries into OpenROAD, ORFS or yosys (instrumentation that stays on the study branch, candidate fixes carried in patches/ one concern each), the edit/measure loop, the noise discipline that makes a runtime or QoR number trustworthy (byte-identical inputs, fixed and witnessed knobs, repeats with 2σ and a stated resolution, an idle machine asserted not hoped), the harness shape (manual flow targets, unit-tested parsers, a report that discovers results and says "not yet measured"), and the PR shape (study/<slug> branch, the finding as the title, graphs and tables in the body with images committed to the branch, raw data as a CSV comment, a closing comment). Use when asked to "study", "measure", "find out where the time goes", "A/B a knob or patch", or to document design decisions that go into an upstream PR.
---

## What a study PR is

A study answers one question with data and is published as a pull request
that is **opened to be read, then closed**. The PR body is the report. The
branch carries everything needed to re-take the numbers: harness, patches,
raw results, figures. Nothing merges from it; anything durable is split into
its own PR first (one concern per PR). There is **no write-up in the tree**,
no `.md` under `docs/` or `ideas/`: a table typed by hand rots the first time
the campaign is re-run, and the report generator is what keeps a partial
study from reading as a complete one.

Precedents to copy the shape from: #965 (gpl runtime), #968 (threads
policy), #958/#963 (pre-route pessimism, and its merged harness under
`test/pre_route_pessimism/`), #966 (two probes, no BUILD at all).

## Two kinds of patch, two homes

A study patches OpenROAD, ORFS or yosys for two different reasons, and they
must not be mixed in one file:

| kind | purpose | where it lives | fate |
| --- | --- | --- | --- |
| instrumentation | timers, counters, extra reports; changes no result | the study branch only, as a `patches/00NN-*-instrument-*.patch` or a BYO checkout | dies with the branch; never an upstream candidate |
| candidate fix | makes something faster or better | `patches/00NN-<tool>-<concern>.patch`, one concern per file, wired into `MODULE.bazel` (`archive_override(patches=…)`) or `ORFS_PATCHES` in `orfs_source.bzl` | measured alone; if it wins it is a listed upstream candidate, if it loses it is written up and **not carried** |

Every arm that claims to measure a fix runs a **real binary** built with the
patch through the module graph, not a hypothesis. Each candidate patch gets a
header saying what it fixes, that it is not upstreamed, and how it retires,
plus a Chesterton's Fence paragraph in the PR body: why the existing code
looked reasonable, so the next reader does not draw the same wrong
conclusion. Instrumentation should extend a pattern the tool already has
(rsz's `utl::DebugScopedTimer`, ORFS's `report_metrics`) rather than invent
one. Whether it gets a `patches/` file or stays in a checkout, its output is
what the harvester parses, so pin its format before running arms.

Upstream repositories stay read-only: candidates are **listed** in the body
with their measured effect, never opened. The human decides when.

## The edit/measure loop

- Iterate with a bring-your-own binary (`byo-openroad` skill) or a deployed
  `_deps` tree; record arms with the carried patch through the module graph.
- Time from the log, not from bazel: `--@bazel-orfs//:log_timestamps`
  stamps every line with elapsed seconds, and a cached stage rebuilds for
  free, so a bazel wall clock measures the cache. Use the tool's own runtime
  lines (`RSZ-0505` style) and progress tables as the primary signal, `perf
  record` on the main thread as the cross-check that the timers add up
  (a BYO build wants `--copt=-g1 --copt=-fno-omit-frame-pointer`).
- Preflight the code path before an hours-long run (`orfs-deps-preflight`):
  a `SKIP_*` default that routes around the thing under test produces a
  clean, fast, meaningless number. For repair questions, the traps in
  `repair-timing-grt` apply.
- Big reproducers that cannot be committed go in a bazel-orfs GitHub release
  and are linked from the body.

## Where the time goes

Profiling the wrong slice of a run, or comparing the wrong pair, has
produced confident numbers that were wrong. These rules come from
measuring XiangShan on asap7.

- **Profile the whole stage.** A short sample is not a stage share. A 60 s
  sample of XSTile's global route put 89 % in the parasitics estimate; the
  whole-stage profile put it at about half, and the 1.48× fix that followed
  was sized from the second. Record the whole stage at a low rate (`perf
  record -F 19 --call-graph fp`), cut it into phases with the log's `Took N
  seconds:` lines, and print a timeline: busy cores and top symbols per
  20–60 s.
- **The main thread is the critical path.** If its samples add up to the
  step's wall time, the step is paced serially, and anything that only frees
  other threads saves CPU, not wall time. Splitting OpenSTA's parasitics lock
  cut cts's futex share from 42 % to 5 % and its CPU by about 40 %, but cts's
  wall time moved 2 %.
- **Name the kernel time.** With `kernel.kptr_restrict=1`, the default, a
  hot kernel address shows up unnamed while every core looks busy. A human
  sets `sysctl kernel.kptr_restrict=0`. Then classify the spinlock samples by
  their kernel path (futex, page reclaim, faults) and attribute each to the
  first frame in our code. That turned "22 % at one kernel address" into one
  mutex with two callers.
- **Probe the scaling before the stage.** Time the operation on a loaded
  checkpoint at 1, 8, 24 and 48 threads, with user and system time from
  `/proc/self/stat`. If system time climbs while wall time stops falling, it
  is contention. Each point takes minutes; a stage run takes hours.
- **Compare first calls with first calls.** The first query in a session
  pays one-time lazy setup: on XSTile, constant propagation (107 s) and the
  clock network (48 s). Comparing a first call with a later one once read
  as 5.2×; the like-for-like ratio was 2.2×.
- **A reader/writer lock does not fix contention under libc++.**
  `std::shared_mutex` is a mutex plus condition variables, so every reader
  still takes a mutex; it measured slower than the plain mutex. Splitting the
  data into independently locked shards is what scaled.
- **Measure where the code runs before trusting a micro-benchmark.** A 12×
  component speedup on 10k-pin nets is worth about 1 % of a stage whose nets
  are already buffered. Look up the component's share of the real steps
  first.
- **List what a parallel loop finds built lazily.** Caches that fill on first
  use break a parallel loop: `Network::drivers`, constant propagation, the
  clock network, Flute's lookup table. Complete them serially before the
  threads start. Under TSan, a report whose top frames on both accesses are
  inside libomp comes from its unannotated barriers; a report with our code
  on top is real.
- **Look for whole rebuilds inside per-edit paths.** An `ensure…` under a
  per-net update rebuilds global state once per edit: every clock repeater
  rebuilt the whole clock network, 685 s of XSTile's cts. A counter of calls
  against useful answers (3.78 M estimates, 0 skipped) shows whether the
  expensive question ever changes the answer.

## Noise discipline

A number without these is an anecdote:

1. **Byte-identical inputs.** Build the stage input once and share it via
   `previous_stage` (see `study_arm` in `test/pre_route_pessimism/arms.bzl`);
   only the arm's variable changes.
2. **Fixed, witnessed knobs.** Pin `-threads` for every arm and pin the
   process with `taskset`; read the knob back from the log
   (`ORD-0030 Using N thread(s)`) and **discard** a sample whose witness
   disagrees with its arm rather than averaging it in.
3. **An idle machine, asserted.** Refuse to record when the 1-minute load
   average exceeds a threshold at arm start, and store `loadavg_at_start` in
   every result. A concurrent compile turned 1.8 s of placement into 16.8 s.
4. **Repeats, 2σ, resolution.** Report individual repeat values, not a mean.
   Spread is 2σ; the resolvable difference at `k` runs per arm is
   `2σ·sqrt(2/k)`. Inside it the verdict is **"did not resolve"**, never
   "no effect". 2σ of a single run is zero, which is honest.
5. **QoR as a hash where none is claimed, as picoseconds where some is.** A
   byte-identical ODB (or ORFS's `result_sha1`) is the strongest statement a
   change can make. Where QoR moves, quote `clk_period - WNS` in ps plus TNS
   and area, never a percentage of WNS. A design that closes before the step
   under test measures nothing about it.
6. **Tens of seconds per case.** A 5 s baseline drowns in noise; pick
   vehicles where the step is long, or build a synthetic sweep.
7. **One result file per sample** `(design, stage, arm, repeat)` so a campaign
   is resumable and a new arm appears in the tables by being run.
8. **Localize a stage delta to the command that changed.** Between single
   runs, XiangShan steps the change does not touch varied by up to 13 %. A
   stage-level difference only counts when the command the change affects
   shows it in the log's `Took N seconds:` lines and the other commands stay
   flat. Frontend's cts looked 9 % faster overall; the command itself was 7 %
   faster.

## Harness shape

Under `test/<study_slug>/`:

- `BUILD.bazel` with every flow-running target `tags = ["manual"]`
  (`bazelisk query` proves it), and non-manual `py_test`s over every parser.
- `campaign.py` (run arms, idle gate, pinning, resumable results),
  `harvest.py` or `elapsed.py` (parse logs into JSON), `report.py`
  (generate the PR body's tables from whatever `results/` holds),
  `plots.py`.
- The report **discovers** results; no result is a declared build input.
  With `results/` deleted, `report.py` fails with "run the campaign first",
  and a section with no data renders as **"Not yet measured"**.
- Results and figures under `docs/studies/<slug>/` (or
  `test/<slug>/results/`), committed on the study branch. If the raw data is
  a few hundred rows, a fenced ```csv comment on the PR is enough and nothing
  is committed under `results/` (#968).
- Probes that load an ODB source `stage_src.tcl`: `RESULTS_DIR` derives from
  the package **declaring** the run, so a probe declared elsewhere fails with
  `ORD-0007`.

## The PR

**Branch** `study/<question-slug>`, with the upstream PR number appended when
the study is about one (`study/size-down-fanout-11320`). Commits use a
`study(<area>):` scope. Never delete the branch: the body's image URLs point
into it.

**Title**: the finding as a sentence, `study: where a single global placement
spends its time, with the patches it points at`. Not the question.

**Body**, in this order:

1. Disposition paragraph, first line, bold: *This is a documentation PR: it is
   here to be read, then closed.* Name what it carries (patches, harness,
   figures) and where anything durable went (`#NNN merged`).
2. TL;DR / the finding, in the form an upstream PR can quote.
3. Method: unit of measurement, machine (cores, SMT, memory), thread pin,
   repeats, what was held byte-identical.
4. Results: **every quantitative claim in a table**; a figure's alt text
   states the claim. Recurring shapes: per-arm
   `wall | delta | 2σ | verdict | same result`; per-serial-item attribution
   `item | wall | what it is`; the quadrant table
   `hypothesis | QoR | runtime | status` where status is one of *carried,
   patches/00NN* / *measured, refuted, not carried* / *not done, upper
   bound X*; cost-to-re-run `axis | target | leaves | wall`.
5. Negative results kept: "What did not move the needle", "Three things
   this rules out". A refuted patch gets its numbers and the reason the
   evidence misled.
6. Limits and caveats, written before anyone asks.
7. Upstream candidates: `PR-to-be | patches | measured effect, alone`, with
   the Chesterton's Fence paragraph per patch. Listed, not acted on.
8. Reproducing: fenced `sh` with the exact bazel lines, the `_deps` deploy,
   the plot regeneration, and the traps hit on the way.

**Images**: commit PNG/SVG to the branch and reference them by **pinned-SHA
raw URL** so later commits do not move them:
`https://raw.githubusercontent.com/The-OpenROAD-Project/bazel-orfs/<sha>/docs/studies/<slug>/fig.png`.
Relative paths break on a closed PR. For small charts, a ```mermaid
`xychart-beta` block or an ASCII bar chart renders in the body with no asset.

**Comments**: raw samples as one fenced ```csv comment with the host line
and column semantics above it, so every table can be recomputed without
re-running. The **closing comment** states intent and what stays reachable:

> Closing as intended, reference only. Self-contained: the patches, harness,
> figures and raw data are all on this branch, and the write-up is in the PR
> body above. Infrastructure proposed for merge in #NNN.

## Before pushing

Run the Confidentiality purge from `CLAUDE.md` over the body, the comments,
the figures' text and the committed scripts: no local paths, hostnames or
user names (a machine is "48 threads on 24 cores, 256 GB", not its name), no
private URLs, no ally names. `bazelisk run //:fix_lint` on the branch; the
harness's unit tests pass; `bazelisk query` shows every flow target manual.
