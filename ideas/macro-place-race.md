# The macro-place race: plan and proof obligations

The single-stage `macro_place` that generates a seed distribution with
RTL-MP, scores candidates with a report-only fast global placement,
races them with progressive elimination, and commits exactly one
winner. This file pins the settled design decisions and the
experiments that must prove them, so the plan survives context loss.
Companion to `rtl-mpl.md` (the maintainer-facing why); this is the
what-and-how-to-prove.

Goal axis: **clock period** (one axis at a time; area/power later —
if an axis can't reach the goal alone, the point isn't on the product
Pareto front). Design rule throughout: **no magic knobs** — every
parameter is a dimensionless invariant, a quantity measured from the
run itself, or a constant validated once against ground truth; never
a value searched per design.

## Settled architecture

1. **RTL-MP is a distribution generator.** Its anneal cost is never
   improved (clustered model mid-anneal, sequence-pair space, per-run
   normalization — see rtl-mpl.md §5); it only needs the four
   generator properties: seedable (`-random_seed`, patch 0041),
   re-entrant (0040 / issue #11277), round-tripping output (0042 /
   #11278), injection≡production (0043 / #11279).
2. **Selection intelligence lives in the estimator, which only needs
   to be ranking-accurate, not accurate.** Uniform optimism ranks
   perfectly; rank inversions are the only enemy.
3. **Scoring is report-only.** gpl in score mode writes nothing (its
   sole non-debug `updateDb` is end-of-run and skippable); only the
   winner commits. Consequence: the final .odb is bit-identical at
   any CPU count *by construction* — k deterministic numbers plus one
   deterministic commit, sidestepping parallel-placement determinism
   entirely.
4. **The stopping rule is decision-driven, not convergence-driven.**
   Candidates advance in lockstep through overflow milestones
   (dimensionless, design-independent). Each candidate's remaining
   score movement is bounded by extrapolating its own observed
   trajectory decay (measured, not guessed). Eliminate a candidate
   when its best-remaining-case is worse than the keep-boundary's
   worst-remaining-case; stop when survivors = keep count or all
   cut-line pairs are resolved. Pairs that never separate are
   *interchangeable* — a legal, logged outcome. Compute concentrates
   automatically on hard decisions; zero per-design knobs.
5. **Pruning cascade** (multi-fidelity successive halving):
   internal anneal cost (free, rehabilitated as a coarse prefilter)
   → early-stopped report-only gpl (~15–25s target)
   → full gpl + STA (~210s today)
   → grt only ever validates the shipped winner.
   Example at k=24 keep-6 keep-2: ≈ 24×0 + 6×20s + 2×210s ≈ 9 min of
   scoring vs 84 min flat.
6. **Parallel topology: wide-and-thin to narrow-and-thick.** Start k
   candidates × 1 thread; survivors inherit threads as the field
   shrinks. Fork gives copy-on-write sharing of the loaded design
   across children (the memory-efficient substrate); memory peak is
   at launch (k × per-candidate footprint, measurable from the first
   candidate) and shrinks monotonically; waves under memory pressure
   are legal because the race synchronizes on milestone indices,
   never wall-clock.
7. **Determinism has three layers**, each with its own enforcement:
   (a) scores CPU-count-invariant — the #11262 pattern (int64
   multisets / relaxed atomics, `mt_invariance`-style test per
   threaded loop; NOTE the known latent int64/float overflow
   accumulation in gpl is order-dependent and must get the multiset
   treatment before that loop is ever threaded);
   (b) the race is a pure function of the candidate set — milestone
   -index sync, fixed tie order (seed number);
   (c) odb bit-identity follows from winner-only commit.
8. **Pin placement during scoring**: `global_placement -place_ios` is
   compatible with the scorer's non-TD/non-RD mode; off-track pins
   are irrelevant to a ranking scalar; per-candidate pin adaptation
   mirrors production (io_placement runs after macro place). The
   ladder's "worst accuracy" verdict on -place_ios was *absolute*
   accuracy; ranking accuracy is the open question (E3).
9. **In-process generation amortizes clustering**: cluster/shape
   once, k anneals — removes a large share of the 110–220s
   per-candidate generation that the flow-level walk pays k times.
   Needs re-entrancy (0040). mpl→gpl is a new but acyclic module
   dependency with precedent (mpl→par, gpl→rsz/grt); the Tcl-level
   race in the macro_place stage script is the low-coupling fallback.
10. **Across RTL revisions there is no intrinsic stability**
    (Kahng/Mantik ICCAD'00, Kahng/Reda ISPD'05 zero-change result,
    ISPD'23 RL assessment; our one-site-nudge chaos). Stability is
    engineered: **incumbent as candidate 0**, replaced only when
    beaten beyond delta_tie (hysteresis with a measured threshold).
    Hazard: synthesis-generated macro names (uNNNN) churn across
    resynthesis — match by hierarchy path + master; an unmapped
    incumbent must fail LOUDLY, never silently become a fresh draw.
11. **Cadence** (pin vs sweep): pinned macro.tcl consumed by every
    run (pinning is what makes single runs interpretable: sigma
    0.7–1.4% pinned vs ~25% unpinned); re-race is event-driven by
    content addressing (bazel re-runs the selector action when synth
    changes, cached otherwise); fenced per-stage sub-seed-sweeps
    (the stage_variance walk) refresh noise bands weekly/on-suspicion
    — sums (20+8+8 members, shared spines) instead of cross products
    (20×8×8 flows); the walk's "all" arm audits the additivity
    assumption. Overnight trend plots wear the last-measured band.

## Proof obligations (the data this plan owes)

Each experiment names its data source, success criterion, and cost.
E1 is in flight; E2–E5 come free or cheap off E1's artifacts.

- **E1 — ranking accuracy of objective vs proxy (the money figure).**
  Evaluate walk: 24 archived seed candidates through the production
  tail to grt (overnight, jobs 12–16) + sequential generate pass with
  debug tables for the objective scores (~1.2h) + delta_tie from the
  running stage_variance walk. Render with
  `test/estimation_ladder/score_vs_flow.py`. Success: proxy Spearman
  rho high with CI clear of zero on period-family KPIs; objective ≈
  flat. This gates everything else.
- **E2 — the racing rule, designed offline.** One re-scoring pass
  with per-iteration logs kept → full score trajectories for all 24
  candidates → replay elimination rules offline against both the
  full-convergence ranking and E1's grt truth. Success: cut-line
  pairs resolve by overflow ~0.4–0.5 with the same survivors; report
  iterations saved. Cost: ~30 min compute + analysis.
- **E3 — scorer variants, cheapest ranking-accurate wins.** Grade
  offline (or via ~30-min re-scoring passes): early-stop depth,
  no-STA analytic readout (WA-HPWL + top-decile density + RUDY —
  all already computed inside gpl, RUDY via RouteBase), -place_ios
  vs pre-placed pins, netlist/bin coarsening if needed. Output: the
  ranking-accuracy-vs-cost curve; pick the knee. Best case ~10x on
  the scorer; end-to-end bounded by generation (Amdahl) until item 9
  lands.
- **E4 — parallel topology with patch 0045** (#11262: the density
  scatter was serial at any -threads; our measured 46–48s "thread
  saturation" was that bottleneck). Re-run the calibration's serial
  arms (t8/t16, add t24) with 0045; re-measure the fork arms
  unchanged as control. Success criterion: a topology table for the
  machine class; decides whether the in-process (threaded-sequential)
  shape is competitive with fork — the in-RTL-MP path depends on it.
- **E5 — memory race profile.** Meter report-only gpl-only children
  (expect < the 1.34GB measured with STA); verify peak-at-launch,
  monotone-shrink; derive the wave rule (launch width from measured
  first-candidate footprint).
- **E6 — determinism holds under the race.** Same winner and same
  scores across jobs counts, thread counts, and wave splits (extends
  the 4-arm identical-winner cross-check already observed);
  mt_invariance-style test accompanies any newly threaded gpl loop.
- **E7 — QoR on the goal axis.** Selected vs default A/B at grt,
  verdict against delta_tie (first n=1 numbers exist: macro-path mean
  −11.2%, extremal period +2.9% pending significance); then
  paired-seed A/B; then the design ladder (tinyRocket below, cva6
  above) to test transfer of the recipe, not of any tuned values —
  there are none to tune.
- **E8 — the incumbent mechanism** (later): inject prior winner as
  candidate 0 across an actual RTL edit; verify loud failure on name
  churn; measure hysteresis behavior against delta_tie.

## Status snapshot (2026-08-31)

Done: patches 0040–0043 carried + issues filed (#11277–#11279),
0045 (#11262) carried; selector end-to-end on swerv (k=24, fork -jobs
12, 65 cand/h, 22 min); seed-distribution figure (45% spread, seed 0
worst); first A/B numbers; rtl-mpl.md rewritten with TL;DR; parser
hardening; cross-package previous_stage.
Running: stage_variance_swerv (delta_tie), detached, jobs 16.
Queued behind it: @openroad rebuild with 0045 → E1 evaluate +
generate passes → money figure → E2–E5 → doc/PR updates.
Deliverable shape: the upstream package proposal writes itself from
whatever survives E1–E6 — seedable placer + `-candidates k` +
report-only gpl with exposed scalars + the knob-free stopping rule.
