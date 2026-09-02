# Auto floorplan: retiring the last three magic knobs

Why does a user have to tell the flow DIE_AREA/CORE_UTILIZATION,
ASPECT_RATIO and PLACE_DENSITY? Because each knob is a confession
that an estimator is missing — a human prediction of downstream
behavior standing where a measurement should be. The macro-place
race (`macro-place-race.md`) retires that pattern for macro
placement; this document is the plan for retiring it from the
floorplan itself. Companion reading: `rtl-mpl.md` for why
prediction-shaped knobs fail and measurement-shaped selection works.

## What each knob actually encodes

**PLACE_DENSITY.** Utilization (cell area / core area) is a global
mean, computable from the inputs — ORFS already computes it
(`place_density_with_lb_addon`'s lower bound). PLACE_DENSITY is a
*local cap* on bin packing, and the gap between the two is headroom
for things that have not happened yet: routing demand where wires
will concentrate (a netlist property, not an area property), and
cell growth the flow has not committed — repair_design and
repair_timing insertions, CTS buffers, hold fixing, ECO margin. The
swerv A/B showed repair effort varying between arms of identical
starting area; that growth lands in whitespace the placer reserved
*before knowing how much would be needed*. So the ADDON margin is a
human estimate of the fog. It is also the canonical AutoTuner knob —
the per-design hyperparameter search that the no-magic-knobs rule
exists to ban.

gpl cannot derive it because the correct value is defined by
outcomes gpl does not simulate. It has partial mechanisms —
routability-driven mode inflates cells in congested regions, a
local, dynamic, *measured* density correction — but the global
target survives as an input because nothing in the placer models
repair growth.

**DIE_AREA / CORE_UTILIZATION.** Area cannot be optimized against
the period goal directly: a bigger core always makes period easier,
so any blended objective inflates the die. Area is either a
constraint (a budget handed down) or a frontier axis. The question a
human answers today by hand-shmooing utilization — "what is the
smallest core in which this netlist closes timing?" — is an oracle
query, and the race is the oracle.

**ASPECT_RATIO.** With macros present, the outline decides which
channel structures are even possible; today's value is folklore per
design. It is a raced coordinate like any other.

## The scheme

The race machinery never cared what varies between candidates —
seeds were merely the first coordinate. Extend the candidate space:

1. **Density: measured floor plus a raced ladder.** Keep the
   computed lower bound (it is derived, not guessed). Race a ladder
   of steps above it. The scorer already sees the congestion half of
   the answer (overflow trajectory, RUDY); if E9 shows it is blind
   to the repair-growth half, the scoring pass gains the estimation
   ladder's repair rung (RUN_REPAIR_DESIGN) — a fidelity dial that
   already exists, not new machinery. The winning density also feeds
   RTL-MP's -target_util, so both consumers of the knob are fixed by
   one measurement.
2. **Area: race-as-oracle inside a utilization shmoo.** For a given
   outline, run the macro-place race; ask whether the winner meets
   the period target (with delta_tie discipline — a miss inside the
   noise band is a tie, not a failure); bisect utilization on that
   answer. Output: the smallest area whose raced winner closes, plus
   the period-vs-area frontier as a byproduct. This is the veteran's
   manual methodology, mechanized, with noise bars.
3. **Aspect ratio: raced per area point.** The outline candidates at
   each utilization step differ in aspect; the seed race under each
   outline explores the channel structures that outline permits.
4. **Stopping and selection inherit the knob-free rules** from the
   macro-place race unchanged: dimensionless overflow milestones,
   trajectory-derived movement bounds, dominance elimination,
   interchangeable ties, delta_tie as the only threshold — measured,
   never searched.

## Cost structure

Area/aspect candidates forfeit the shared floorplan spine (each
outline needs its own floorplan, ~30–60s on swerv), but clustering
is a netlist property and amortizes across *all* outlines — the
in-process design's biggest win survives. The search is a shallow
outer loop (a bisection on utilization, a few aspect points) around
the already-priced inner race (~22 min at k=24 today, dropping with
the E3/E4 scorer and topology work). A full auto-floorplan of swerv
class is plausibly an overnight artifact; with the cascade and
early-stop scorer, an evening one.

## What this displaces

- **AutoTuner on these knobs.** Search guesses and re-runs the flow
  end to end per trial; the race measures candidates against a
  ranking-accurate score with a noise floor, reusing shared
  prefixes. Where a knob's value is decided by data, it stops being
  a hyperparameter.
- **The folklore config.mk.** DIE_AREA, ASPECT_RATIO,
  PLACE_DENSITY_LB_ADDON entries hand-carried from design to design
  become outputs: the flow's inputs shrink toward netlist +
  constraints + period target.
- Nothing about constraints changes: fences, halos, blockages, IO
  regions remain inputs — human knowledge enters as constraints the
  race runs inside, never as coordinates (see rtl-mpl.md on manual
  placement).

## Proof obligations

Phase 2 starts only after the macro-place race's E1–E7 hold (a
ranking-accurate scorer is the load-bearing assumption; without it
the oracle answers noise). Then:

- **E9 — density race fidelity** (also listed in
  macro-place-race.md): does the scorer (± the repair rung) rank a
  density ladder consistently with grt-after-repair outcomes? Same
  offline grading pattern as E3, on a density ladder instead of a
  seed population.
- **E10 — the area oracle.** On swerv: bisect utilization with the
  race as oracle against a period target; validate the reported
  minimum-area point by running its neighbors (one utilization step
  denser and looser) through the production tail. Success: the
  frontier point is real within delta_tie; cost of the whole
  derivation stays overnight-class.
- **E11 — aspect sensitivity.** At the E10 area point, race a small
  aspect ladder; success is either a measured preference beyond
  delta_tie or a demonstrated "aspect is a tie here" — both are
  results; folklore values get graded, not assumed.

## Status

Idea stage. Depends on: macro-place race E1–E7 (in flight — E1's
evaluate walk and delta_tie are running as of 2026-08-31), the E3
scorer-fidelity curve, and the E4 topology recalibration with the
carried gpl density-scatter patch (0045 / OpenROAD PR #11262).
Nothing here requires new OpenROAD changes beyond what the race
already carries; the outer loops are flow-side orchestration over
existing rungs.
