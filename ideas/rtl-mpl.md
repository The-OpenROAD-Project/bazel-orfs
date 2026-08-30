# RTL-MP: from auditing the scoring function to replacing the selection

Where the macro-placement work goes next, written down so another machine
can pick it up: what is established, the improvement idea, the OpenROAD
patches it needs (with source pointers), and the swerv_wrapper campaign
that would prove or kill it.

Context: the stage-variance decomposition (PR #866) located the flow's
noise at macro placement — downstream of a fixed placement the flow is
quiet (sigma 0.7–1.4% on multiplier_top), while the placer's response to
its input swings the achieved period ~25%. Choosing a macro placement is
therefore choosing a downstream outcome, and RTL-MP chooses with an
internal annealing cost. The `macro_score` campaign in
`test/estimation_ladder/` audits that cost against what global route
actually delivers.

## Established mechanics (verified against OpenROAD mpl source and by run)

1. **RTL-MP cannot be made to score an external placement.**
   - No evaluate-only entry point exists (`src/mpl/src/mpl.i` exposes
     only the placer, `place_macro`, guidance/halo/blockage setters).
   - The Total Cost it prints is **normalized per run** (norm factors
     sampled per anneal, `SimulatedAnnealingCore<T>::calNormCost`), so
     even its own totals are not comparable across two runs. The RAW
     component values in the debug penalty table
     (`set_debug_level MPL hierarchical_macro_placement 1`) are
     placement properties and are comparable.
   - Forcing the annealer onto a target with per-macro guidance regions
     fails structurally: the SA explores **sequence-pair packings**
     (`SimulatedAnnealingCore<T>::packFloorplan`), and arbitrary
     geometry is not in that space — measured 80–247 um of
     non-compliance, including against the placer's own winner.
2. **`place_macro` rejects `rtl_macro_placer`'s own output**: the placer
   works against the requested CORE_AREA while the instantiated core
   rows snap slightly smaller, so winners can poke a snap residue
   (~0.01 um) past the core top and `place_macro` (MPL-34) /
   `add_guidance_region` (MPL-42) error out on it.
3. **Injection is not production**: `HierRTLMP::run()` seeds a
   temporary std-cell placement (`generateTemporaryStdCellsPlacement`)
   after placing macros; the `MPL-0013` skip path (all macros LOCKED via
   `MACRO_PLACEMENT_TCL`) does not, so an injected placement diverges
   from the production flow downstream even with bit-identical macro
   geometry — measured ~2% on the achieved period. Consequence: a
   selected winner must be materialized by **re-running its generation**
   (deterministic), never by injecting its coordinates.
4. `global_placement -random_seed` defaults to 1, so seed 1 is the
   unseeded flow's own draw — a null, not a sample. `GRT_SEED` works as
   a grt-stage lever; CTS exposes no seed.

## Preliminary audit observations (multiplier_top; final numbers land in this PR)

- P_pick — the probability RTL-MP's default objective picks the better
  of two of its own placements by achieved period at grt — polled at a
  **coin flip** (~0.47 raw, n=19 scored candidates) in the in-flight
  campaign. The objective's favorite was a fence-degraded candidate;
  the flow's best was the wirelength-weight-crippled one.
- **The fog forgives the worst path but transmits the aggregate**: on
  achieved period (max), winners and deliberately scrambled placements
  overlap; on the mean of the sampled worst-25% paths they separate
  cleanly (~20% between strata). A WNS-shaped KPI cannot see macro
  quality; an aggregate can.
- **Effort masking**: repair rescues the period of bad placements by
  spending global-route runtime (members with scrambled placements
  ground for >10x the typical grt time). Runtime (`tail_s`, recorded
  per member) belongs in the KPI menu alongside period and area.

## The improvement idea: distribution + measured selection

Don't fix the objective — replace the *selection*:

1. **Generate** k candidate placements with RTL-MP itself (today:
   CORE_AREA site nudges + RTLMP_*_WT jitter; cleaner with the
   `-random_seed` patch below).
2. **Score** each with a **fast non-timing-driven global placement**
   (the estimation ladder's gate rung: `RUN_MACRO_PLACE=1, RUN_PLACE=1`,
   TD/RD off) in one OpenROAD process using `//fork` — a *post-fog*
   measurement that implicitly prices density and congestion, the terms
   the contest evidence says dominate and RTL-MP's objective lacks.
3. **Select** the winner and materialize it by re-running its
   generation deterministically (see finding 3: never inject).

Best-of-k arithmetic: the expected gain of picking the best of k draws
from a spread sigma is ~sigma·sqrt(2·ln k) — diminishing after k≈10–20.
For A/B comparisons (e.g. a PR gate), pair the candidate seeds between
arms so selection bias cancels.

This is independently validated at competition scale: the winners of the
Partcl × Hudson River Trading macro-placement challenge used exactly
this shape — multi-start seed generation with physical diversity,
GPU-accelerated candidate ranking, pick the winner — and found that
**congestion dominates once wirelength saturates** (they re-tuned their
internal objective to WL + density + 2.5·congestion; the contest's own
proxy is WL + 0.5·density + 0.5·congestion, with finals judged on real
OpenROAD flow outcomes). References:

- Contest: https://github.com/partcleda/macro-place-challenge-2026
- Winner write-up (ArchGen): https://www.archgen.tech/blog/posts/how-we-ranked-first-in-the-partcl.html
- TILOS MacroPlacement (proxy evaluator lineage, BSD-3): https://github.com/TILOS-AI-Institute/MacroPlacement
  — if a literature-comparable proxy column is wanted, vendor the three
  cost concepts (grid HPWL, top-decile density, RUDY-style congestion)
  against ODB directly rather than depending on the protobuf/clustering
  chain; BSD-3 permits either.

## Proposed OpenROAD patches (minimum churn first, with pointers)

Each is independently useful and justified by a finding above; together
they make the selector clean. Develop against a local OpenROAD checkout
via the BYO loop (`OPENROAD_EXE` injection — see `.claude/commands/` /
the byo-openroad workflow) before proposing upstream.

1. **`rtl_macro_placer -random_seed`** (tiny): expose the SA RNG seed so
   the placer is a distribution generator. Entry: `src/mpl/src/mpl.tcl`
   (arg parsing), `rtl_mp.cpp::place` (plumbing),
   `SimulatedAnnealingCore` (RNG init).
2. **Skip-path parity** (small bugfix): when `has_unfixed_macros` is
   false, still run `generateTemporaryStdCellsPlacement` before
   returning (`hier_rtlmp.cpp`, `HierRTLMP::run()` / MPL-0013 path), so
   `MACRO_PLACEMENT_TCL` reproduces production downstream. Fixes the
   measured ~2% injection offset.
3. **Snap-residue containment** (small bugfix): clamp
   `rtl_macro_placer`'s committed macro positions to the actual core
   box (or relax `place_macro`'s MPL-34 check by the manufacturing-grid
   residue), so the placer's output round-trips through its own sibling
   command.
4. **`report_macro_placement_cost`** (moderate): evaluate the objective
   of the placement currently in the DB — unnormalized components (the
   raw values `printResults` already computes:
   `SimulatedAnnealingCore.cpp` / `SACoreSoftMacro.cpp`) without running
   the anneal. This is the missing evaluate API; it also fixes the
   cross-run comparability gap.
5. **Congestion term in the objective** (larger churn; only if the
   audit on a macro-heterogeneous design shows the current objective
   fails there too): RUDY-style H/V demand over bundled nets, per the
   contest evidence. Do 1–4 first; the selector may make this
   unnecessary.

## The swerv_wrapper (asap7) campaign

`multiplier_top`'s 16 identical macros make it the easiest possible
macro problem (pure permutation, regular dataflow); it now serves as the
null-control design. The real test is heterogeneity:

- **swerv_wrapper** (asap7): ~28 SRAM macros in three fakeram sizes
  (2048x39, 256x34, 64x21) — big-vs-small channel formation is where
  congestion physics lives; real timing paths through the memories;
  runtime tractable for populations. The ORFS design dir has RTL +
  LEF/libs ready (`flow/designs/asap7/swerv_wrapper`).
- Ladder: `tinyRocket` (AUTO_MEMORIES, ~a dozen small macros) as the
  fast debug rung below; `cva6` (70% utilization, 5um halos) as the
  stretch rung above.

Steps, in order — each lands as its own PR:

1. `orfs_flow` target for swerv_wrapper in bazel-orfs (source-only, RTL
   and fakeram collateral from the pinned ORFS tree).
2. `stage_variance` walk on it: the design's own noise floor and
   delta_tie (never reuse multiplier_top's numbers).
3. `macro_score` audit on it: baseline P_pick / AUC / regret for the
   default objective on a heterogeneous design — the number the
   improvement must beat.
4. The selector (generate k → fast-GPL score → re-run winner) as a
   `macro_select` walk reusing the same fork machinery; score the
   fast-GPL column with the same audit math (its P_pick vs the
   default objective's, selection regret, wall-clock cost per
   candidate).
5. With the `-random_seed` patch (BYO OpenROAD binary): repeat 3–4 with
   seed-generated populations, which removes the core-nudge confound.
6. Verdict table per KPI — achieved / aggregate / area / **runtime**
   (`tail_s`; effort masking makes runtime a first-class quality axis)
   — and the go/no-go: does measured selection beat objective-trust by
   more than the design's delta_tie, at a nightly-affordable cost?

## KPI guidance carried over from the audits

- Gate on **aggregate** period statistics, not extremal ones: the max is
  a noise hostage and blind to macro quality; the worst-25% mean
  transmits it.
- Report **runtime and std-cell area** next to period: the flow trades
  both for period (effort masking), and a period-only verdict credits
  the trade as free.
- Always publish the resolvable delta next to any verdict; ties below
  the measured noise floor are ties. `inconclusive` is a legal answer.
