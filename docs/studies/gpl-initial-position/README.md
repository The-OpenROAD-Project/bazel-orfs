# Where global placement starts from

This directory holds the method and the reproduction commands. The
findings live in the pull request body, generated from the checked-in
result JSONs — a table typed by hand rots the first time the campaign is
re-run.

## The question

Global placement puts every placeable instance somewhere before it
solves anything. Today that somewhere is the core center, or whatever
the ODB happens to hold, and which of the two you get depends on a flag.

Nobody has measured it. `placeInstsCenter()` arrived with the RePlAce
import (OpenROAD `456cde4187`, 2020-08-11) carrying the comment
*"normally, initial place will place all cells in the centers"* — no
citation, no test. The policy has been reversed four times since:

| when | change | stated reason |
| --- | --- | --- |
| 2024-06 | OpenROAD #5253: use the ODB position if present | PR body empty |
| 2024-07 | #5253 follow-up: ODB only when skipping initial place | "you might pick up the skip_io result" |
| 2025-06 | OpenROAD #7644: back to the core center | "the **expected** behavior … is the center"; "I do **not expect** any functional change" |
| 2026-01 | OpenROAD #9353: ODB by default, add `-force_center_initial_place` | "some users … **expect**"; "which is **non intuitive**" |
| 2026-01 | ORFS `bab0134ebd`: pin `-force_center_initial_place` flow-wide | "maintain default behavior" |

No QoR number is attached to any of them. The one time evidence spoke —
#9353's unit tests changed results — the tests were updated.

So the question is not "is the center best?" but the one before it:
**does the starting distribution change QoR or runtime at all, above the
noise a seed already produces?** If it does not, ORFS's flow-wide opt-out
is a sentry in an empty garden and can go. If it does, nobody chose the
value it is set to.

## What ORFS actually does, which is two different things

| stage | script | start position |
| --- | --- | --- |
| `3_1_place_gp_skip_io` | `global_place_skip_io.tcl` | **ODB locations** — no `-force_center_initial_place` |
| `3_2_place_iop` | `io_placement.tcl` | `place_pins` on 3_1's result |
| `3_3_place_gp` | `global_place.tcl` | **forced to the core center**, unconditionally |

3_3 therefore discards 3_1's converged placement on every design in the
flow. That is why `shipped` and `center` are separate arms here: the gap
between them is the cost of the split, and it is a result in itself.

## The arms

One binary, selected at run time by `-initial_position_mode`
(`patches/0066-openroad-gpl-initial-position-mode.patch`, study branch
only; passing no mode takes the shipped path unchanged).

| arm | start |
| --- | --- |
| `shipped` | ORFS as it stands — the baseline |
| `center` | the core (or region) box center, at both calls |
| `odb` | the ODB location when placed, else the box center |
| `corner_ll`, `corner_ur` | a corner of the box |
| `uniform` | uniform over the box, drawn from `-random_seed` |
| `gauss_tight`, `gauss_wide` | normal at the box center, σ = 0.10 / 0.25 of the box |
| `spread` | a deterministic R2 low-discrepancy sweep of the box |
| `anchored` | the centroid of the fixed pins the cell sees through its nets |

`spread` is the control that separates two different hypotheses: if
`center` and `spread` differ, the problem is that every cell starting on
*one point* is degenerate for a bound-to-bound net model, not that the
center is the wrong point.

## Endpoints, ordered by how much flow stands in between

1. `gp_hpwl_final`, `gp_iterations` — what global placement optimizes,
   and a runtime proxy that does not depend on machine load. One step
   from the change.
2. `wirelength`, `grt_overflow` at global route. Congestion is carried
   because OpenROAD #7581 was a routability failure traced to a
   placement change; a study reporting only timing would have missed it.
3. `min_period = clk_period - WNS` at global route, in picoseconds.
   Never as a percentage of WNS.

## Sizing

The noise floor is not assumed. It is recomputed from PR #977's 402
published samples on this same host:

| design | clk | `min_period` 2σ | as % of clock | `gp_hpwl_final` 2σ |
| --- | ---: | ---: | ---: | ---: |
| aes | 380 | 7.44 ps | 1.96 % | 1.57 % |
| ethmac | 1000 | 7.00 ps | 0.70 % | 1.36 % |
| gcd | 310 | 2.82 ps | 0.91 % | 2.81 % |
| ibex | 1000 | 4.73 ps | 0.47 % | 0.65 % |
| jpeg | 545 | 11.72 ps | 2.15 % | 0.91 % |
| uart | 270 | 5.71 ps | 2.11 % | 2.62 % |
| **median** | | | **1.43 %** | **1.46 %** |

Resolution at `k` seeds per arm is `2σ·√(2/k)`, so `k = 16` resolves
≈0.51 % of the clock per design and ≈0.15 % pooled over 12 designs.
Quadrupling `k` only halves it, which is why 16 and not 64.

Nine arms on twelve designs is 108 comparisons, and a 2σ per-comparison
threshold produces roughly five confident-looking rows from nothing at
all. So a per-design verdict is never a finding on its own: an arm
counts only when at least **4 of 12** designs resolve **in the same
direction**, which holds the family-wise rate near 0.4 %. The threshold
is computed, not chosen, and is printed in the report next to the rate
it buys. Where the design count cannot buy the rate, the verdict reads
**underpowered** rather than better or worse.

## Discipline

* **Byte-identical inputs.** One `//:deps` tree per design; every sample
  runs inside it under its own `FLOW_VARIANT`, so all arms share the
  synthesis and floorplan bytes.
* **A witness per arm.** The patch logs the mode it ran; a sample whose
  log does not name the arm it was run as is **discarded**, and the
  discarded count is printed. A flag that never reached the command line
  otherwise produces a clean run whose numbers match the default's.
* **`NUM_CORES` fixed** across every sample. PR #968 established that
  thread count does not change results on these designs, so samples run
  several-wide.
* **Runtime claims are separated.** Wall time is only quoted from
  `--serial` samples, which run one at a time and refuse to start on a
  busy machine. `gp_iterations` is machine-independent and is the
  runtime endpoint everywhere else.
* **Determinism, checked rather than assumed.** The same arm at the same
  seed, run twice, must produce a byte-identical `3_3_place_gp.odb`.
  Without that every delta in the study could be run-to-run variation
  wearing an arm's name. Measured on `asap7/gcd`, seed 7:

  | arm | run twice | first 20 hex of SHA-1 |
  | --- | --- | --- |
  | `shipped` | identical | `4190ad315c53591dde91` |
  | `spread` | identical | `b37d69c5f4eb0cedf839` |
  | `odb` | identical | `61e3d7fef31b37b10290` |

  Identical on repeat, and different between arms, which is both halves
  of the control: the flow is deterministic, and the knob is live.

## Reproducing

```sh
# One deployed tree per design; costs synthesis and floorplan once.
bazelisk run //:deps -- @orfs//flow/designs/asap7/gcd:gcd_place

# Tier 1: the place stage, every arm. 16 seeds, 32 for the arms whose
# start position is itself a draw.
bazelisk run //test/gpl_initial_position:campaign -- \
    --tree "$PWD/tmp/@orfs/flow/designs/asap7/gcd/gcd_place_deps" \
    --platform asap7 --design gcd \
    --seeds 1-16 --stochastic-seeds 1-32 \
    --tier place --cores 4 --jobs 6 \
    --out-dir "$PWD/tmp/gpl_ip/results"

# Tier 2: continue to global route, for the arms tier 1 could not settle.
#   --tier tail --arms shipped,center,spread,anchored --seeds 1-8

# Wall time, quotable: one at a time, on an idle machine, pinned.
#   --serial --max-loadavg 2.0 --cpu-list 0-7 --arms shipped,center

# The determinism control: same arm, same seed, twice.
for rep in r1 r2; do
  make do-place FLOW_VARIANT=det_$rep GPL_RANDOM_SEED=7 NUM_CORES=4 \
      GLOBAL_PLACEMENT_ARGS="-initial_position_mode spread"
done   # the two 3_3_place_gp.odb must be byte-identical

bazelisk run //test/gpl_initial_position:report -- \
    --results "$PWD/tmp/gpl_ip/results"
bazelisk run //test/gpl_initial_position:plots -- \
    --results "$PWD/tmp/gpl_ip/results" --outdir docs/studies/gpl-initial-position

# 51 unit tests over every parser and the statistics. No ORFS checkout,
# no deployed tree, no flow.
bazelisk test //test/gpl_initial_position:all
```

With `results/` empty the report exits saying to run the campaign first,
and any section without data renders **"Not yet measured"** — a partial
campaign cannot read as a complete one.

## Traps hit on the way, so the next person does not

* A fresh `FLOW_VARIANT` fails with `ORD-0007` unless the frozen prefix
  is copied into it first: the flow reads `2_floorplan.odb` from the
  variant's own directory, not from `base/`.
* Leaving a previous run's outputs in a variant directory lets `make`
  decide the stage is already built. The sample is then harvested from
  the *old* run under the new name — the one failure here that produces
  a plausible number instead of an error. `prepare_variant()` deletes
  and recreates rather than updating.
* `GLOBAL_PLACEMENT_ARGS` reaches both `3_1` and `3_3`, so an arm is a
  flow-wide policy and not a change to one call. That is deliberate, and
  it is what makes `shipped` a distinct arm from `center`.
* `utl::checkKey` has no `std::string` specialization, so a string
  option cannot be plumbed through it without widening a shared helper.
