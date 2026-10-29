# Timing and power metrics as a separate action, off the critical path

Status: **checked on gcd, answered yes for cts, grt, route-end and
final; restructuring not started.** A fresh process on a stage's saved
.odb/.sdc reproduces that stage's metrics bit for bit at default
settings. Harness: `test/metrics_split` (manual).

## Problem

ORFS computes the timing and power metrics inside each stage, before
the stage writes its .odb, so the next stage waits for them. Since
#1433 (carried 0157/0158, ORFS #4766) bazel-orfs skips them by
default (`SKIP_REPORT_METRICS=1`) and keeps only the free ones (area,
instance counts, the tools' own counters). A flow that wants timing and
power in `metadata.json` pays for them on the critical path, every
stage: a timing update, a power analysis, four filtered register path
searches. On gcd that is 55-710 ms per stage; on ibex under
OpenROAD-SYN, synth's report_metrics ran for over two hours.

## What was checked (asap7/gcd)

1. **No side effect.** Metrics on vs off: byte-identical .odb at every
   stage (also with `DETAILED_METRICS=1`).
2. **Reproducible from the saved stage.** `report_stage.tcl` loads the
   stage's .odb/.sdc with ORFS's `load_design`, redoes the stage's
   parasitics (placement for place and cts, global_routing for grt, the
   6_final.spef for final), and calls `report_metrics` under
   `utl::open_metrics`:

   | stage | keys equal | differ |
   |---|---|---|
   | place (3_5 detailed place) | 38 | 0 |
   | cts | 40 | 0 |
   | grt | 40 | 0 |
   | final | 40 | 0 |

   The whole .rpt text matches too. The only differences seen were in
   switching power, and only when `DETAILED_METRICS=1`: its power
   report before `repair_timing` leaves stale activities in the
   process, so the in-stage number after repair is the wrong one
   (cts switching 0.0001944 in-stage vs 0.000196048 both in-stage
   without DETAILED_METRICS and in the separate process).
3. **Rollup already decoupled in bazel-orfs.** No PnR stage action
   reads an upstream .json (`private/rules.bzl`, include_logging);
   `generate_metadata` is the one action that gathers every stage's
   .json (LoggingInfo.jsons) and runs genMetrics.py, which merges
   `logs/N_*.json` by glob. A report action writing `logs/4_*.json`
   with metrics stage `cts__{}` rolls up unchanged.

## Idea

Per stage, an optional report action: src = the stage target, reads
the stage's .odb/.sdc (and spef for final), writes `N_<stage>_report.json`
into the stage's LoggingInfo.jsons. The next stage depends only on the
stage action, so the report runs in parallel with it; generate_metadata
is the join. In-stage `SKIP_REPORT_METRICS` stays 1.

## Restructuring needed

ORFS (an upstream change, not an option):
- a supported way to run report_metrics on a stage's results: a
  script per stage, or one script taking the stage, that loads the
  .odb/.sdc, sets `utl::set_metrics_stage` to the stage's prefix, and
  estimates parasitics the way the stage did. write_endpoint_slack and
  open.tcl already hold that stage-to-parasitics logic; synth-report
  (synth_metrics.tcl) is the precedent for synth.
- file names under the `N_*.json` globs genMetrics.py already merges.

bazel-orfs:
- an orfs_report-like stage (sibling of generate_metadata) per stage,
  its .json added to what generate_metadata collects.

Not reproducible from what bazel-orfs keeps, to decide:
- floorplan's report is on 2_1 (before tapcell and pdn), global place's
  on 3_3, resize's on 3_4: mid-target states, not outputs (only
  2_floorplan.odb and 3_place.odb are). Report on the stage-end .odb
  instead (tapcell changes the area a bit), declare the intermediates,
  or drop those reports.
- DETAILED_METRICS reports (before repair in cts and grt) are
  in-process states by design; they stay in-stage and stay off.
- final's IR drop (analyze_power_grid) is not report_metrics; it stays.

## Impact

Turnaround for flows that want timing and power metrics: the report
cost leaves the critical path. Cost: a second load of the design per
stage (memory and time; minutes on XiangShan-sized designs, which
`scale-to-memory` has to count). Not measured beyond gcd.

## Effort

Medium: one ORFS script and make target (upstream PR), one bazel-orfs
stage rule, the place/floorplan decision above.
