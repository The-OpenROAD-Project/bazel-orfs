# The `<flow>_estimate` report

Every `orfs_flow()` that runs synthesis grows two targets:

- **`<name>[_variant]_estimate`**: a deterministic, one-to-two-minute
  estimate of what the design can achieve at its configured floorplan
  parameters — estimated achievable clock period, the macro-path
  channel, utilization, density against its computed bound — built
  from the **synthesis output**: the floorplan is initialized
  in-script from the same variables the production floorplan stage
  reads, macros placed by the production placer, then a
  non-timing-driven, early-stopped global placement.
- **`<name>[_variant]_estimate_run`**: the same script as a
  `bazelisk run` executable taking run-time `KEY=VALUE` parameter
  overrides — one point in floorplan-parameter space per invocation.

```sh
bazelisk build //test/smoketest:lb_32x128_asap7_estimate
cat bazel-bin/test/smoketest/lb_32x128_asap7_estimate.json

bazelisk run //test/smoketest:lb_32x128_asap7_estimate_run -- \
  CORE_UTILIZATION=10 PLACE_DENSITY=0.6 OUTPUT=$PWD/point.json \
  LOG_DIR=$PWD/logs
```

Because the estimate builds its own floorplan, it is independent of —
and parallel to — the flow's entire physical implementation, and it
can measure parameter points the flow never runs. It cannot perturb
any flow artifact.

This document is the thesis behind the report: why a *fast, less
accurate* signal is the right tool for gating changes, what the
numbers mean, how far to trust them, and the math of using them.

## A flow result is a draw

A global-route PPA number is a draw from a population. Kahng and
Mantik measured this across industry tools a generation ago
(*Measurement of Inherent Noise in EDA Tools*, ISQED 2002):
meaning-preserving perturbations of a tool's input move results by
amounts comparable to claimed optimization improvements. Comparing a
pull request against merge-base with single runs is reading lottery
tickets; the honest comparison needs a seed sweep and a measured
noise floor. That is slow — hours per side.

The field has spent thirty-plus years failing to produce a fast,
accurate global-route estimator, and this report does not claim one.
It claims something weaker that turns out to be sufficient: a
**deterministic, ranking-accurate-ish estimate used differentially**.

- **Deterministic**: the same input produces the same JSON,
  bit-for-bit. An estimate delta between two commits has no sampling
  noise of its own — unlike a flow delta, which needs a noise floor
  just to be readable.
- **Differential**: pre-route estimates are uniformly optimistic (the
  central finding of the estimation ladder this report grew out of).
  In a this-commit-vs-merge-base diff, the shared bias cancels; what
  remains is the response to the change.
- **Cheap baseline**: outputs are content-addressed. The merge-base's
  JSON already exists in cache from its own build; a PR builds only
  its side, and the comparison is a file diff. Built nightly, the
  same artifact is a trend line at roughly one percent of flow cost.

## The math of gating with a fast, imperfect signal

Model development as a guided random walk toward a PPA goal G. Each
candidate change has a true effect δ (positive = improvement). The
gate observes δ̂ = δ + ε, where ε has spread σ_f — the estimator's
*transfer error* through placement, CTS and routing — and merges when
δ̂ exceeds a threshold t. Merged work is audited by an overnight seed
sweep with resolution d_tie (the design's measured noise floor);
regressions larger than d_tie are caught and reverted.

Progress per candidate evaluated:

    v = p⁺ · μ⁺ · A⁺(σ_f, t)  −  p⁻ · E[ |δ| · A⁻ ; |δ| < d_tie ]

where p⁺, μ⁺ describe the improving candidates, A⁺ their accept rate,
and the second term — the only *permanent* damage — is bounded by
p⁻ · d_tie. Candidates to goal: n* = G / v. Three results follow:

1. **The overnight audit truncates the downside.** No bad merge can
   cost more than d_tie permanently; the gate's errors are transient.
   Positive drift is guaranteed whenever p⁺ · μ⁺ · A⁺ > p⁻ · d_tie —
   a condition met with room to spare by any change population whose
   improvements are meaningfully larger than the noise floor. The
   audit, not the gate, is what makes fast-and-imperfect safe.
2. **Large effects are exponentially safe in both directions.** The
   probability of missing an improvement of size δ decays as
   exp(−δ²/2σ_f²); the same for a large regression slipping through —
   and the audit catches it anyway. Only the interval (−d_tie, +σ_f)
   is murky, and everything in it is small by definition. Missed
   improvements can be relitigated; hidden sub-floor regressions
   accumulate as bounded drag that the nightly trend line exposes as
   deviation from expected drift.
3. **Throughput wins by orders of magnitude.** Illustrative numbers
   (σ_f = 15ps, d_tie = 10ps, t = σ_f; 30% improvements at +20ps, 30%
   regressions at −20ps, 40% null): the fast gate needs ~46 candidates
   to the slow gate's ~30 for the same goal — and ~1 hour of gate
   compute against ~300. The gate stops being the bottleneck; the
   walk's speed becomes limited by candidate supply.

The gate does not need to be right. It needs to keep the drift
positive at maximum candidate throughput, with correctness delegated
to the cheap audit and to the exponential tails.

## Protocol

1. Estimate delta ≫ transfer error → actionable verdict, act on it.
2. Delta below resolution → a tie *at this fidelity*; escalate to the
   full flow with seed pairing and delta_tie discipline, or accept
   the tie.
3. Overnight: seed sweep over merged work; revert what exceeds the
   noise floor.
4. The report carries data, not advice: absolute numbers with their
   bases, no recommendations. Gating policy belongs to the consumer.

## What is in the JSON

| field | meaning |
|---|---|
| `clock_target` | period of the first clock, STA units |
| `est_achievable_raw` | clock_target − wns after the estimate placement; **pre-route optimistic, differential use** |
| `wns` | worst reg2reg slack at placement parasitics |
| `utilization`, `core_um2`, `cell_um2` | area occupancy of the floorplan |
| `num_macros` | macros in the design (placed by the floorplan stage) |
| `macro_paths_mean`, `macro_paths_worst`, `macro_paths_sampled` | the macro-path channel — the KPI macro placement actually controls; zeroed when the design has no macros |
| `macros_pinned` | whether MACRO_PLACEMENT_TCL held the macro placement constant — see "Macro designs" |
| `density_lb_addon` | the computed lower bound plus the configured addon; also the estimate's placement density |
| `gp_overflow_target` | the early-stop point (see below) |
| `params` | the floorplan parameters in force, under their **exact ORFS variable names** — a chosen point is directly consumable by config.mk pin machinery |

Timing values are OpenSTA units (`time_unit`); the report's own
wall-clock cost is in the run log's `Elapsed time` line.

## Division of labor: recommendations here, mechanics in ORFS

This report is the *oracle* half of floorplan-parameter automation:
`_estimate_run` produces self-describing points, a session (human or
AI) assembles the Pareto front and picks a recommendation, and ORFS's
pin machinery writes it into config.mk (`pinAutoFloorplan.py` and the
`<name>_auto_floorplan_pin` target of OpenROAD-flow-scripts PR #4487,
which preserves the design's existing rect-vs-utilization form and
density form in place). bazel-orfs computes recommendations; it never
writes config.mk. `checkPareto.py` (same PR) then guards merged work:
a trade along the front passes, a dominated point fails.

Constraints imported from that PR's measured negative results:
utilization enters only as constraint satisfaction — the smallest
core no worse than the incumbent — never blended into a period
objective (measured rho −1.0 on gcd for the blended form); and every
parameter ladder may report "did not resolve" against its noise
floor, which keeps the incumbent. Its in-flow scorer measures after
global route (realistic, noise floors 22–32% of clock); this oracle
measures pre-route (optimistic, deterministic, minutes) — the
differential protocol is what licenses the cheap one.

## Macro designs

The floorplan built here includes the production macro placer's
single default draw — and macro placement is chaotic in the netlist,
so on macro designs an *unpinned* estimate delta between two commits
carries placement-draw variance (measured at up-to-25%-scale swings)
on top of the change being measured. `macros_pinned` says which
regime a JSON was produced in: with `MACRO_PLACEMENT_TCL` set (stock
ORFS), the draw is held constant and deltas are clean. The
macro-path fields are the channel macro placement controls
(measured: ~300ps spread across draws while general paths tie);
racing and selecting the pin is the macro-placement campaign's
business (PR #868).

## Calibration status and provenance

Measured, with data committed in the macro-placement campaign
(bazel-orfs PR #868 and `test/estimation_ladder/`):

- Early stopping at overflow 0.6: ranking power of the placement
  saturates there (trajectory replay over 24 candidates; rho within
  noise of full convergence at ~70% of the iterations).
- STA-free ranking: raw HPWL ranked post-route macro-path timing at
  rho +0.67 vs the full instrument's +0.72 (n=24, overlapping CIs).
- Estimator-vs-flow ranking across configurations: Kendall tau
  0.80–0.87 (the estimation ladder's fronts).
- Area fidelity: estimate-to-route rho ≈ +0.5–0.65 across two
  designs.
- Determinism: placements and scores bit-identical across thread
  counts, execution shapes and a compiler/binary change (24/24).

Pending, tracked in the campaign plan:

- σ_f for logic deltas — the PR-vs-merge-base transfer error — via a
  backtest over historical or synthetic changes (E14). Until it
  lands, treat est_achievable deltas as ordering evidence with the
  config-ranking tau above as the prior, not as calibrated
  magnitudes.
- A validated absolute correction (the raw estimate is uniformly
  optimistic; differential use does not need the correction, absolute
  use does).

## Own your scoring function

The impossible thing was a universal, accurate estimator — so the
achievable thing is a local, owned, revisable ranking function. Write
your own scoring for your design and the development phase you are
in, and plan to revise it as the design progresses. The measured
basis for each clause:

- Corrections fitted on one design transfer worse than no correction
  at all (the estimation ladder's transfer study — its most flexible
  fit memorized its own design and then lost to nothing on the next).
- The live KPI moves with the operating point: at loose constraints
  the period axis is dead and area/macro-path slack are what a score
  can see; near the design's capability wall, period wakes up. Gate
  on the axis that is alive where you are.
- The noise floor is a property of the operating point too (measured
  48.8 -> 15.4 -> 7.3 ps across one design's clock sweep), so even a
  perfect scorer's thresholds go stale as constraints tighten.

This report ships a general-purpose default; treat it as the
starting point the protocol calibrates, not as the answer.

## Limits

- **A speedometer, not a map**: the estimate tracks *whether* the
  achievable period moved, not which path moved it (measured
  recall@10 of critical paths barely above chance). Localization
  needs the flow.
- Pre-route blindness: routability catastrophes, hold and CTS
  pathologies are invisible here.
- The reg2reg path group comes from the platform SDC; designs without
  it fall back to the unconstrained worst path.
