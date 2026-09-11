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

## Decisions log

- 2026-09-11: knobs become no-ops rather than being removed; one PR per
  knob; suite is asap7 plus sky130hd; timing axis is minimum clock period;
  noise bands from rules-base.json history; second study branch.
