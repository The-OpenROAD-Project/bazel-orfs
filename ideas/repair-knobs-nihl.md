# Retiring the repair_timing knobs: a no-human-in-the-loop policy, proven

Charter for the campaign, written 2026-09-11 so the goal does not drift.
The evidence lives in closed bazel-orfs study PRs; the deliverable is
OpenROAD pull requests that lead with the answer.

## Framing

Andrew Kahng's no-human-in-the-loop (NIHL) vision has a very concrete
first target: the knob whose value a human picks by staring at paint.

`repair_timing` has several. `TNS_END_PERCENT`, `SKIP_LAST_GASP`,
`SKIP_GATE_CLONING`, and `-verbose` were each cheap to add, and each moved
a cost onto every user of the flow: the only way to set one is to run the
flow twice per design and pick. The number that comes out is
design-specific. Nothing is learned from it; it does not transfer to the
next design or survive the next optimizer change; it sits in a config.mk
as a fossil of one afternoon. Ten of the asap7 designs pin
`TNS_END_PERCENT` to 100 this way.

Each such knob is a missing policy. The optimizer already has the
information the human was reading off the log: whether the last endpoint
gained anything, whether WNS moved in the last hundred passes, whether a
move type has been accepted lately. A rule that reads that trajectory
makes the same decision the human would, per design, at runtime, with no
one watching.

Why this has not happened: retiring a knob means proving, across the whole
suite, that the replacement dominates today's default. That proof is
sixty machine hours and a week of someone's attention, and nobody is paid
to watch it. Adding a knob is an afternoon. So knobs accumulate and the
flow needs an oracle that does not exist. This is the disaster of the
commons, and the policy itself needs NIHL to get its data, or the data is
never gathered.

What changes the economics is making the staring unattended and the proof
generated: arms that run themselves behind an idle gate, a witness that
refuses a sample for the wrong knob, a report that writes the table, and a
harness the next person can re-run when the optimizer changes. Machine
time is cheap; attention is why it never happened.

## What is measured and settled (study/repair-timing-runtime)

- Census, 16 asap7 designs, floorplan/cts/grt, unpatched binary: setup
  repair is 51-63% of those stages on the designs that grind; hold repair
  is under three seconds in total.
- Attribution, instrumented binary, five vehicles (riscv32i, jpeg,
  mock-alu, ibex, coralnpu): the repair work itself is 1-5% of a pass.
  The rest is the STA required-time update after each accepted move
  (40-67%), the `-verbose` progress row (10-48%; 88% of coralnpu's 221 s
  floorplan call), and at grt the incremental global-route parasitics
  plus their re-estimation on journal restore (22-34%).
- The progress row is a fix, not a knob: OpenROAD #11387, two commits,
  output unchanged, 264 rsz tests pass. Carried here as patches 0067 and
  0068 until the bump that brings it.
- Knob arms, three repeats, resolution under 5 s: every knob that wins
  somewhere loses somewhere. `TNS_END_PERCENT=5` saves 25-55% on three
  vehicles and costs mock-alu grt 31% and 1104 ps of TNS.
  `SKIP_LAST_GASP` saves 14-26% at riscv32i and mock-alu grt and costs
  ibex cts 2.8 ps of WNS. `SKIP_GATE_CLONING` saves 28% on ibex cts and
  costs riscv32i grt 22% and 5.4 ps. `SKIP_BUFFER_REMOVAL` and
  `MATCH_CELL_FOOTPRINT` do nothing measurable. That table is the case
  that these are missing policies, not tuning problems.

## The policies, one carried patch each

| knob | it guesses | the rule that reads the trajectory instead |
|---|---|---|
| `TNS_END_PERCENT` | when endpoints stop paying | stop the worst-first endpoint sweep after K consecutive endpoints yield no accepted move and no WNS or TNS gain |
| both | when a phase is done | end a phase after two 100-pass windows in which neither WNS nor TNS moved (patch 0069) |
| `SKIP_LAST_GASP` | whether a second phase pays | run last gasp only if the main phase ended while still gaining |
| `SKIP_GATE_CLONING` | which move types pay | drop a move type for the rest of the phase once its acceptances over a window of N attempts are zero, or worsen WNS |

The knobs stay accepted and inert. K and N are fitted once on riscv32i and
jpeg, then frozen before any other design runs, so the policy is not tuned
on the set that judges it.

Those three are fixed-threshold approximations. The candidate meant for
upstream is the **return controller** (patch 0074): per phase, at each
hundred-pass window, measure what the window bought in TNS and WNS against
what it cost in seconds, remember the phase's best rate, and stop after two
consecutive windows below 1% of that best with WNS flat. Last gasp runs
only after a phase that was still paying when it ran out of endpoints. A
move type tried a hundred times in a phase with no acceptance is retired
for the phase. Every constant is a ratio of the run's own measurements or
a scale the optimizer already uses; there is no value a user could set per
design. Phase A runs it beside the threshold set; Phase B judges whichever
of the two dominates.

## The bar: dominance over today's default on all asap7 and sky130hd designs

Per design (20 asap7, 7 sky130hd), default versus policy, full flow to
`6_final`:

- Timing axis is **minimum clock period**, `clock - WNS`, in picoseconds.
  Not "closure": with no clock uncertainty and one corner, which side of
  zero a design lands on is an artefact of the period ORFS picked.
- Minimum clock period, TNS, area, power and wire length each within the
  design's own **noise band** or better. The band is the residual spread
  after detrending that metric's history in the design's
  `rules-base.json` across ORFS git (asap7 ibex: 127 rebase commits since
  2020). `genRuleFile.py` pads with fixed, invertible transforms, so the
  thresholds de-pad into measured values. The residual includes real
  algorithm changes and so errs toward accepting a change; raw deltas stay
  in the table beside the verdict. Short histories fall back to the
  twelve-seed spread.
- DRC, placement and antenna counts: not worse at all.
- Total flow wall: not worse on any design, better where repair grinds.
- Where the policy has nothing to do, the ODB is byte-identical, and the
  hash says so.

All 27 designs pass, or the policy goes back to Phase A. One failing
design is a result, not a caveat.

## Phases

- **A. Find it.** Five asap7 vehicles, three repeats, floorplan, cts, grt.
  Arms: base, each policy alone, all combined, and the oracle (the best
  knob setting already measured per design). The trap cases decide it:
  mock-alu grt and ibex cts. About 10 machine hours.
- **B. Prove it does no harm.** All 27 designs, full flow, default versus
  combined policy, one run each, judged by the bar above. About 25 machine
  hours.
- **C. Quantify.** Three repeats on the designs that moved, so the headline
  carries a 2σ. About 10 hours.

## Deliverables, and what is not pitched

- A closed bazel-orfs study PR (`study/repair-policy`, forked from
  `study/repair-timing-runtime` so the harness comes along): the verdict
  table, the trajectories, the oracle comparison, the raw data, the noise
  bands. Cited as evidence. Never pitched: nobody will run bazel-orfs, EDA
  engineers use `make` in ORFS, and that is fine.
- One OpenROAD PR per knob retired, policy on by default, flag kept as a
  no-op. Each body leads with the suite table and links the study.
  Opened only on the human's order.
- ORFS mop-up later, one PR deleting the pinned `TNS_END_PERCENT` and
  `SKIP_*` lines, once the OpenROAD side has landed.

## Third study: yield order first, then the knobs (approved 2026-09-14)

#982 settled that no rule reading the trajectory of the worst-first sweep
dominates the default: return per pass is heavy-tailed because the sweep
is ordered by slack (importance), not by what an endpoint will pay
(yield). The literature never orders work that way: TILOS picks moves by
sensitivity, Lagrangian sizers by multipliers that carry every endpoint's
criticality, Held by a cheap global pass before local search, and all of
them stop on convergence of a monotone objective. So the third study
changes what is swept before it asks when to stop. Branch
`study/repair-yield`, forked from `study/repair-policy`.

The deliverable is one closed bazel-orfs study PR carrying all data, from
which one OpenROAD PR per knob is split, each with a TL;DR of the
situation today, the problem, and the fix, referring to the study.

1. **Phase 0, diagnosis** (patch 0078, instrumentation only): one line
   per endpoint visit with entry and exit slack, WNS and TNS, passes,
   seconds, first and last improving pass, path depth, candidates,
   attempts, accepted and net moves by type, and the exit reason; one
   line per phase with the slack quantiles. Full flow on the four
   designs that defeated every policy (mock-alu, jpeg, ibex,
   sky130hd/riscv32i) plus riscv32i. Questions it answers: are
   mock-alu's jackpot passes endpoints that gained late or endpoints
   reached late; which cts endpoints does an early stop hand to grt on
   jpeg and sky130hd/riscv32i and what do they cost there; why does
   ibex's closing endpoint sit 1000 passes in.
2. **Yield-ordered sweep** (C++ in rsz, one patch): a triage pass
   estimates each violating endpoint's achievable gain per cost from a
   cheap local model without committing; the WNS endpoint stays pinned
   first; the sweep runs in descending estimated yield, re-estimating
   only endpoints whose fan-in changed. The return curve becomes
   monotone by construction.
3. **`TNS_END_PERCENT`: keep the intent and the interface, change the
   semantics, aim to remove.** The flag stays accepted. Its meaning
   becomes a quantile of the endpoint slack histogram below the worst
   endpoint, in units of that histogram's spread, never the clock
   period, which varies along the flow. With a monotone sweep the
   natural stop is marginal return, which needs no value; Phase B
   measures the option honoured under the new semantics and the option
   ignored, and if ignoring it dominates everywhere the value retires.
4. **`SKIP_LAST_GASP`**: last gasp prints the same progress rows as the
   main phase with the estimated remaining yield, and stops itself when
   that yield is below what a pass costs. Flag accepted, inert.
5. **`SKIP_GATE_CLONING`**: the clone move gets a real estimate that
   rejects a clone whose fanout split cannot reach the required slack
   before any trial commit, so a design with nothing to clone pays one
   sweep of arithmetic. Flag accepted, inert.
6. **Suite**: all asap7 and sky130hd designs as the bar demands, plus
   nangate45, sky130hs, gf180 and ihp-sg13g2 as evidence the policy is
   not tuned to two platforms; full flow; default against each patch
   alone and combined; three repeats on movers; verdict.py and the
   existing noise bands.

Not in scope: any mechanism that carries knowledge between runs (the
knobs are being removed because they ask the user to do that), and any
learned policy that needs training runs per design.

## Decisions log

- 2026-09-14, 17:00: 0079 fails on the design it was built for. mock-alu
  cts: 1346 to 914 passes but 45.6 to 52.1 s and WNS -272.7 to -282.1;
  grt: 970 to 757 passes, 39.5 to 56.0 s; flow +29 s, min period -11 ps.
  Two causes, both in the data. First, a pass on a fresh endpoint costs
  more than a pass in a grind: STA per pass 0.028 to 0.040 s in cts,
  parasitics per pass 0.015 to 0.025 s in grt, and every dry probe
  restores its journal (restore 4 to 11 s), so 30% fewer passes cost
  more seconds. Second, TNS per pass is blind to WNS: the worst decile's
  visits that bought "6% of the gain" bought the whole 31 ps of WNS,
  one small step per visit, and a two-pass probe does not see a step
  that only shows once the endpoint is the worst. Ordering by measured
  yield is refuted as built; the measurement stands as the study's
  negative result with its profile. What the traces do support without
  changing the order: the dry tail of a visit. Patch 0080 gives every
  endpoint that does not carry WNS a patience of three dry passes
  instead of fifty (the WNS endpoint keeps fifty: riscv32i grt's first
  gain comes at pass 31). The v3 trace's patience table on the five
  vehicles sets the constant before Phase B; the analytical estimate in
  the same trace decides whether visits that cannot pay can be skipped
  outright, which is the only way to cut the fresh-pass cost.

- 2026-09-14, 16:20: two traps, both mine. A compile check of a study
  patch is a bazel build of OpenROAD, and the running campaign's next
  deploy builds whatever MODULE.bazel and the patch files say at that
  moment: sky130hd/riscv32i's "Phase 0" run went out with 0079 in the
  binary (set aside under tmp/repair_timing_runtime/mislabeled, read as
  a first look) and the trace-v2 arm never ran because the build's load
  kept the idle gate shut for its 900 s limit. Rule from here: swap a
  patch file only right after a design has started, and build only
  then; never while an arm waits at its gate. Worth a line in the
  study-pr skill. That first look at 0079 on sky130hd/riscv32i: cts
  35.6 to 25.9 s and TNS -82.5 to -71.1 ns, grt 117 to 192 s with TNS
  -158.6 to -136.9 ns, flow +57 s. The profile says why: incremental
  parasitics per pass 0.039 to 0.144 s and journal restores doubled.
  Every probe opens a fresh region and every dry probe restores it, and
  on a grt stage that is a global-route update each time; the legacy
  grind stays in one region. Passes are not the currency in grt. Next:
  the v3 trace records an analytical size-up estimate per path driver
  (the liberty arithmetic SizeUpGenerator already does) so the study can
  ask whether an estimate that costs no pass predicts what a visit pays.

- 2026-09-14, 15:15: context for the pitch. rsz already has a phase
  pipeline (`repair_timing -phases`, default LEGACY then LAST_GASP with
  an implicit CRIT_VT_SWAP): WNS, WNS_PATH, WNS_CONE, TNS,
  ENDPOINT_FANIN, STARTPOINT_FANOUT, REROUTE, GLOBAL_SIZING are
  accepted. The TNS phase sweeps worst first with an adaptive patience
  (6 dry passes, growing to 25 on success); none of the phases orders
  endpoints by what they pay. 0079 changes the LEGACY phase because
  that is the default every ORFS user runs; the same sweep as a phase
  token is the fallback if maintainers prefer it. Also from Phase 0: of
  781 paying non-first visits across four designs, 37 show their first
  gain after pass 2 and none of those carried WNS; the largest (ibex grt,
  584 ps, first gain at pass 47) is what decides whether a two-pass
  probe needs a second-chance round.

- 2026-09-14, 14:45: Phase 0 on four designs shows three regimes, and
  one policy shape covers them. mock-alu: the gain sits in endpoints
  the worst-first order reaches late, each paying in one or two passes.
  jpeg: the gain is in the worst decile and comes as a slow grind (one
  to two ps per pass over 30-100 passes), with the fifty-pass patience
  wasting a quarter of cts on eight "stuck" visits. ibex: one endpoint
  holds 93-99% of the gain and seven hundred visits are overhead. In
  every regime a paying endpoint shows its first gain within two passes
  (95-100% of the gain), and a visit's gain correlates with nothing
  known before it (rank correlation with entry slack 0.06-0.32, jpeg
  floorplan aside). Decision: patch 0079, probe-then-drain. The worst
  endpoint keeps its legacy budget; every other endpoint gets a two-pass
  probe worst first; endpoints still paying go into a heap by TNS gained
  per pass and drain best first in two-pass rounds; the phase ends when
  the heap is empty. The fix-rate fence stays; if it fires during the
  probes it ends the probing and the heap drains. No last-gasp change in
  this patch (one concern). The trace v2 (every improving pass) decides
  whether a two-pass round loses late gains.

- 2026-09-14, 13:30: first Phase 0 reading (mock-alu). The cts jackpot
  at passes 1000-1200 is not endpoints that gained late: it is endpoints
  reached late by the worst-first order (sweep index 98-183 of 643,
  entry slack -13 to -53 ps), each closing in 1 to 18 passes with its
  first gain in pass 1 or 2. The 126 worst endpoints took 80% of the
  passes for 7% of the gain and ended "no_change". A one-pass probe
  finds 72% of the gain for 21% of the passes, a two-pass probe 100%
  for 32%. Ordering, not stopping, is the lever, as the literature says.
  Second reading, from #982's own data: where defer-and-revisit lost
  wall, it lost it in detailed route (sky130hd/aes +130 s in 5_2_route
  with cts and grt faster and better) or in grt inheriting a different
  cts netlist. Any policy that changes the netlist meets this; the wall
  axis has no noise band because the flow is deterministic on identical
  inputs. Decision: measure the wall band under an equivalent netlist,
  the default with GPL_RANDOM_SEED 2 and 3 on the 20 fast designs, and
  judge wall against that band, as QoR is judged against the history
  band. Queued behind Phase 0 (tmp/run_seed_band.sh).

- 2026-09-14, 12:30: third study approved (this section). Phase 0 runs
  first and reports before any policy code is written; no compute on
  items 2 to 5 until its tables are read.

- 2026-09-14, 06:15: closed as bazel-orfs #982, reference only. Verdict:
  no trajectory-based stopping rule dominates the default across the 20
  designs; the three candidates fail in three directions; the knobs are
  Pareto trades; the lever is the cost of a pass. Next study: the STA
  update after each accepted move (40-67% of a pass) and grt's
  incremental parasitics (22-34%).

- 2026-09-13, 21:50: defer-and-revisit (0077) fails the bar on wall: 12
  of 20 pass; eight designs are 2-13% slower (sky130hd/aes +121 s,
  sky130hd/riscv32i +65 s, sky130hd/jpeg +61 s, ibex +50 s, jpeg +46 s)
  with QoR equal or better on all but none. Deferring reorders the
  sweep; the reordered sweep produces a different netlist and the later
  stages pay for it, and the promised revisit rarely happens because the
  legacy fix-rate exit ends the phase first. Three trajectory rules,
  three failures in three different directions. The verdict of the
  study: no rule that reads the repair trajectory dominates today's
  default across the suite; the knobs encode Pareto trades, and the
  universal lever is the cost of a pass. Phase C repeats run for the 2σ
  on the movers; the study closes tomorrow morning.

- 2026-09-13, 17:45: coralnpu's default full flow was killed after 11
  hours in detailed route (iteration at 70% with 4572 violations after
  52 minutes, on 24 threads). The full-flow arm cannot carry coralnpu
  within this study's budget; it stays in the record for the stage-level
  arms (#978 and Phase A) and leaves Phase B. The slow group is therefore
  dropped entirely: Phase B is the 20 fast designs.

- 2026-09-13, 10:15: the slow group is cut after coralnpu (both
  candidates already fail the bar on the fast group; the slow group
  cannot change the verdict). A sixth candidate, 0077 defer-and-revisit,
  is the first whose failure mode is not "stopped before the win": an
  endpoint that has not improved within the phase's own patience (twice
  the median passes the improving endpoints needed, at least three,
  legacy until five have improved) is put aside with its passes counted
  and revisited after the sweep with the rest of its budget. Every
  endpoint is still visited, no endpoint gets more passes. Acceptance
  test: mock-alu cts must keep its passes-1000 gain. Then the fast group
  full flow, then Phase C repeats (default, v3, 0077) on the movers.

- 2026-09-13: the two hierarchical BLOCKS designs, asap7/aes-block and
  asap7/riscv32i-mock-sram, cannot run the full flow on a floorplan
  deployment: macro placement fails with MPL-0003 (no valid tiling)
  under the default arm before any repair runs. A harness limit, the
  same on both arms; they leave the suite, which is 25 designs.

- 2026-09-13, 05:40: the stall exit (0069) fails the bar too. Fast
  group: 18 of 20 pass; jpeg is 4% slower and sky130hd/riscv32i 17%
  slower, both with QoR equal or better. The stage split says why:
  stopping cts earlier leaves work for grt, whose passes cost several
  times more (incremental global-route parasitics), and on
  sky130hd/riscv32i detailed route takes 77 s longer on the different
  netlist. So the two candidates fail in opposite directions: the
  controller (v3) wins jpeg grt (-51%) and loses mock-alu; the stall exit
  holds mock-alu and loses jpeg and sky130hd/riscv32i. The finding of the
  policy study is that no trajectory-based stopping rule dominates the
  default across the suite: each is a Pareto trade, like the knobs it was
  meant to retire. The universal lever is the cost of a pass, not its
  count. The slow group runs under the default and the controller for the
  record at scale, then Phase C repeats on the designs that moved, so the
  wins and the losses carry a 2σ; the 0069 slow group is dropped.

- 2026-09-13: the return controller v3 fails the bar. Phase B, fast
  group, 20 designs: 15 pass, riscv32i and ibex -8% and -24% with every
  KPI better; but mock-alu is 26% slower with TNS 9.2 ns worse. Its cts
  trajectory shows why any rate-based stop is unsafe: windows of 495,
  350, 65, 1, 113, -80, -62 ps, then at passes 1000-1200 three windows
  of ~4000 ps each. Return over the worst-first sweep is heavy-tailed and
  not monotone, so a rule that stops on recent return will sometimes cut
  before the jackpot. Round two runs the exact stall exit (0069, two
  windows of no movement at all), the most conservative rule, on both
  groups; the controller finishes the slow group for the record. The
  verdict's criteria were also corrected from the first table: hold WNS
  is judged like closure, power gets a 1% tolerance since ORFS gates no
  power metric, and a wall difference under max(5 s, 2%) is a tie on a
  single run.

- 2026-09-12: Phase B runs the return controller v3 (patch 0074: per
  window, deterministic, first window at phase start, two empty windows
  end a phase, last gasp under the same rule, the run's best window kept
  across phases). One-repeat check against the rows-only control: grt
  riscv32i -91% and closed (+15.5 ps), jpeg -51% with TNS +224 ps, ibex
  -74% with WNS +0.1 ps, mock-alu identical; cts riscv32i -54% and still
  closed. Nothing worse on any axis. The threshold set (0073) is fast but
  loses closure on riscv32i cts and TNS on jpeg, so it is not carried
  into Phase B.

- 2026-09-12: patch arms are flow-level, not stage-level. A patched
  binary rebuilds the earlier stages too (place runs repair_timing), so
  a policy arm's cts and grt inputs differ from the control's; on
  riscv32i grt the control starts at 860 violating endpoints and the
  stall-exit arm at 767. Stage tables for policies are read as "each
  arm on its own inputs"; the judgment is Phase B's full flow, as the
  bar already said. The worst-slack query alone (0075) reproduces the
  control exactly, so no stale-timing effect is in play.

- 2026-09-12: 0071 (skip last gasp after a main phase that stopped for
  lack of return) is refuted alone: it reproduces the knob's own losses
  (jpeg cts -655 ps TNS, jpeg grt -1420, mock-alu cts -1.1 ps WNS, grt
  -2.5 ps). The legacy fix-rate exit fires on most designs after pass
  1000, and last gasp's looser acceptance still finds TNS after it. So
  the return controller (0074) runs last gasp under the controller
  instead of skipping it. 0070 (endpoint-yield gate, K=20) is refuted
  alone on riscv32i cts, where it ends the sweep before closure. 0072
  (move-type budget, N=200) is inert: its alone arm reproduces the
  rows-only numbers on every vehicle and stage to within 1%, with
  identical QoR, so no move type ever reaches a window of attempts with
  zero acceptances. Cloning's cost is not an acceptance-rate problem.

- 2026-09-12: K and N frozen at 20 and 200 after the fit on riscv32i and
  jpeg (cts and grt, one run each, all four threshold policies on). N in
  {100, 200, 500} changes nothing on any stage: the move budget is not
  where either the wall or the QoR moves. K in {10, 20, 50} changes only
  the wall on riscv32i grt (18, 22, 129 s) with identical QoR. The QoR
  deltas the set carries on these two designs (riscv32i cts -3.7 ps WNS,
  jpeg cts -655 ps TNS, jpeg grt -1420 ps TNS) do not move with either
  constant and are attributed by the alone arms.

- 2026-09-11: noise bands are taken over the history since 2025-06-01
  (the whole history is an era: sky130hd/aes area moved 9x since 2021).
  A metric whose recent history has fewer than three recoverable points
  (setup WNS on designs that met timing throughout, coralnpu and cva6
  entirely) gets no band, and any worsening on it counts as worse, which
  is the strict direction. Bands live in
  docs/studies/repair-policy/noise_bands_since_2025-06.json.

- 2026-09-11: knobs become no-ops rather than being removed; one PR per
  knob; suite is asap7 plus sky130hd; timing axis is minimum clock period;
  noise bands from rules-base.json history; second study branch.
