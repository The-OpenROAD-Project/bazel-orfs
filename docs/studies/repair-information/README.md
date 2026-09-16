# Does `repair_timing` help because of its policy, or its information?

This directory holds the method and the reproduction commands. The
findings live in the pull request body, generated from the checked-in
result JSONs by `test/repair_information/report.py` — a table typed by
hand rots the first time a campaign is re-run.

## The question

ORFS repairs timing three times, against two different pictures of the
same wires:

| stage | script | parasitics |
| --- | --- | --- |
| resize (pre-CTS) | `resize.tcl`, gated by `ENABLE_PLACE_REPAIR_TIMING` | `estimate_parasitics -placement` |
| cts | `cts.tcl`, gated by `SKIP_CTS_REPAIR_TIMING` | `estimate_parasitics -placement` |
| grt | `global_route.tcl`, gated by `SKIP_INCREMENTAL_REPAIR` | `estimate_parasitics -global_routing` |

The usual story is that the last one is the good one because global route
knows where the wires went. If that is the mechanism — if the *information*
is the lever rather than the policy — then a throwaway global route before
the earlier repairs should let them decide as well, and the flow is leaving
QoR on the table by repairing twice against a Steiner estimate.

Three questions follow, and the cheapest one governs the others.

1. **Does the better instrument rank endpoints differently?** A repair
   handed the same ordering spends its budget on the same endpoints, and
   then the quality of the numbers behind the ordering cannot change what
   it does. This is a necessary condition, and it costs no flow re-runs.
2. **How cheap can the throwaway route be?** `global_route` already takes
   the arguments a trial route needs; the question is how much of the
   information survives at each price.
3. **Is any of it bigger than the floor?** Two floors, and they are
   different numbers — see below.

## What is measured

### Rank agreement, not error in picoseconds

The probe (`endpoint_slacks.tcl`) reports one worst slack per endpoint
under exactly one instrument, and `rank_agreement.py` scores each
instrument against the routed design's own extracted SPEF:

* Spearman ρ over the whole endpoint set;
* top-k overlap — of the k endpoints the SPEF says are worst, how many
  does the candidate also put in its worst k;
* the reference-critical endpoints the candidate ranks outside its top k,
  which are the paths a repair driven by it never looks at.

A model wrong about every slack by a constant ranks perfectly, and for
driving a repair that is all that is asked of it. Slack error is reported
as a diagnostic, never as the verdict.

Endpoints rather than paths because the endpoint set is what survives the
flow: repair inserts buffers and CTS builds a tree, so instances and nets
differ between two stages of one design, but a register's data pin is
still the same pin at `4_cts` and at `6_final`.

### The trial-route ladder

Every rung is the same CTS ODB, routed differently (`probes.bzl`):

| rung | `global_route` arguments |
| --- | --- |
| `cheapest` | `-allow_congestion -congestion_iterations 1 -infinite_cap -skip_large_fanout_nets 100` |
| `no_overflow_loop` | `-allow_congestion -congestion_iterations 1` |
| `few` | `-allow_congestion -congestion_iterations 5` |
| `stock` | `-congestion_iterations 30` — what ORFS runs |

Three things about these arguments are load-bearing:

* `-allow_congestion` is **required**, not a tuning choice. `grt::have_routes`
  — the gate `estimate_parasitics` itself uses — rejects a congested route
  without it, and the probe would fail with `EST-5` as though no route had
  happened.
* `-congestion_iterations` is checked positive, so 1 is the floor, not 0.
* `-infinite_cap` is the cheapest possible route and also the one that
  cannot see a detour. `pre-route-pessimism` found contention is the
  necessary ingredient for placement and global route to disagree at all,
  so the cheapest rung may measure what the placement estimate already
  measured, at the cost of a route. That is the point of running it.

`pin_access` is timed separately from the route: ORFS runs it before
`global_route`, so a trial route that skipped it would not be the same
operation — and if pin access dominates, a cheaper congestion setting buys
nothing.

### The two floors

`noise_floor.py` reports both, and they are not the same bar:

* **the CI tolerance bar** — `rules-base.json` records a *padded
  threshold*, not a measurement: `genRuleFile.py` pads setup worst slack
  by 5% of the clock period. A change smaller than that will never fail a
  rule, whatever it does to the design.
* **the measured floor** — 2σ over repeats of the same arm with only the
  placement seed varied, and `2σ·sqrt(2/k)` as the difference resolvable
  at k runs per arm. `pre-route-pessimism` measured 2σ = 47.5 ps for
  `min_period` at global route on a contended asap7 design, 3.6× the
  spread of the placement estimate it is supposed to be correcting.

An effect must clear the measured floor to be a result, and the tolerance
bar to be worth deploying. Inside the resolution the verdict is **"did not
resolve"**, never "no effect".

## Reproducing

```sh
# One design: build every rung and copy the JSONs into the source tree.
bazelisk run //test/repair_information:update_gcd

# The report, from whatever results exist. A rung that was never run is
# named as missing rather than dropped.
bazelisk run //test/repair_information:report -- \
    --results $PWD/test/repair_information/results

# The parsers, which are the only non-manual targets here.
bazelisk test //test/repair_information/...
```

Every flow-running target is `manual`: each one loads a stage ODB and
routes it.
