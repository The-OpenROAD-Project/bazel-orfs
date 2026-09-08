---
name: repair-timing-grt
description: Investigate OpenROAD global-route repair_timing correctly — the grt "grind"/timeout, hold- and setup-buffer insertion. Covers why a skip-repair (fast) grt measures nothing about repair, why repair_timing must run inside global_route.tcl on the pre-GR ODB, how to split the grind into setup vs hold before blaming either, why the win is measured as clk_period-WNS in picoseconds rather than as a percentage of WNS, and why a design that closes measures nothing about a repair knob. Use when a grt stage times out or runs for hours, when a change is meant to affect repair_timing, or when reasoning about hold vs setup buffer insertion at global route.
---

## Goal

Get a *trustworthy* answer about `repair_timing` at global route: whether it
grinds, why, and whether a proposed change moves it. The traps below have each
wasted hours-long runs; clear them all before drawing any conclusion.

## Trap 1 — a skip-repair / fast grt measures nothing about repair

When the question is about **repair_timing** (the grt grind/timeout, hold- or
setup-buffer insertion), do NOT use a fast/skip-repair grt flow
(`SKIP_INCREMENTAL_REPAIR=1`, `SKIP_CTS_REPAIR_TIMING=1`, or a
`grt_skiprepair`-style extract). It skips `repair_design` / `repair_timing`
entirely — it only global-routes and estimates parasitics — so a clean, fast
exit tells you **nothing** about whether repair grinds. Using it to "test the
grind" is structurally meaningless.

The fast-grt flow is built for clock **skew / parasitic re-measurement**, where
skipping repair is exactly what you want. For anything about repair, run the
FULL grt with repair enabled (`SKIP_INCREMENTAL_REPAIR=0`).

## Trap 2 — repair_timing needs the live global-route structures

`repair_timing` must run **inside `global_route.tcl`, on the pre-GR ODB.** It
needs the live global-route structures (GR grid, congestion, routing guides)
that are **not** persisted in the saved post-GR ODB. So you cannot bolt
`repair_timing` onto a saved post-GR ODB in a fresh session — it must happen in
the same openroad session as `global_route`, which is exactly what
`global_route.tcl` does:

```tcl
# (shape of the flow script)
global_route
if { !$SKIP_INCREMENTAL_REPAIR } {
  repair_design_helper
  repair_timing_helper
}
```

To test repair on a **modified netlist**, stage the PRE-GR ODB (the CTS-stage
output) into the grt extract and run the grt stage with
`SKIP_INCREMENTAL_REPAIR=0`, so `global_route` rebuilds the structures and
repair runs live. Do NOT reuse a saved post-GR ODB.

## Trap 3 — measuring the win in WNS, or in percentages of it

Report **`min_period = clk_period - WNS`**, and report differences between
arms in picoseconds of that. Never a percentage of WNS.

Near closure WNS is a small number, so a percentage of it is dominated by
the clock you happened to pick rather than by anything the flow did: the
same absolute improvement reads as 5% or 500% depending on the constraint.
`min_period` is the quantity a designer actually trades against, it stays
roughly invariant to the constraint (which is why it is comparable across
arms at all), and a delta in it is a delta in what the design can run at.

`check_pareto.py` already takes this position for its period axis —
`clock - WNS`, never WNS itself, with the reasoning written out there — and
`test/pre_route_pessimism/stage_ladder.tcl` reads it the same way.

Two corollaries when the arms are repair settings:

* **A percentage of a percentage is worse.** "The gap moved 17%" where the
  gap is itself a ratio of periods is unreadable. Quote the periods.
* **Watch the constraint-invariance assumption.** It is only roughly true.
  Measured on one design, `min_period` at global route moved 322.3 -> 322.0 ps
  between a 1000 ps and a 330 ps clock (invariant to 0.1%), while at
  placement it moved 287.3 -> 285.7 ps between 330 and 290 (0.6%). Fine for
  comparing arms, not fine for treating a sub-percent difference as signal.

## Trap 4 — repair stops at WNS zero, so a closing design measures nothing

`repair_timing` works until the violation is gone. Once WNS reaches zero it
stops, so **every setting of a repair knob reaches the same floor** and the
achieved period cannot separate them. What differs is runtime.

This is not the same as "nothing to repair", and the difference matters when
calibrating a study:

* A design that closes *without* repair exercises no repair at all. Any knob
  measured on it reports zero because nothing ran.
* A design that closes *because* repair worked exercised it fully. A knob
  swept there still cannot move the period.

Both look identical in a post-repair slack report, which is the trap: reading
positive WNS and concluding "the knob does nothing" conflates them.

**And repair's recovery is not a fixed budget you can calibrate past.** It
tracks the constraint. Measured on one design at global route, over two
clocks 25 ps apart:

| clock | min_period before repair | after repair | recovered |
| --- | --- | --- | --- |
| 290 ps | 322 ps | 289.7 ps (WNS +0.29) | 32 ps |
| 265 ps | 322 ps | 265.8 ps (WNS -0.85) | 56 ps |

Repair stopped just shy of the target in both cases, so post-repair
`min_period` mostly echoes the clock rather than reporting a property of the
design. Tightening the clock does not "get past" repair; it just makes repair
work harder for the same near-zero result.

So **calibrate to slightly negative WNS so repair is still working when it
stops** — that is achievable and is what you want. But do not expect the
achieved period to separate repair settings at such a clock: it cannot, by
construction. Expect the separation in **runtime**, which is what a coverage
knob like `TNS_END_PERCENT` claims to trade anyway, and report both.
Achieved period only becomes informative at a clock repair demonstrably
falls short of, which may be far tighter than the point WNS first goes
negative.

And turn off what you are not studying. Last gasp is the long tail of
`repair_timing` and there is no reason to expect a `min_period` cliff in it,
so `SKIP_LAST_GASP=1` buys back the runtime that makes an ensemble
affordable.

## Trap 5 — split the grind into setup vs hold before blaming either

The grind can be **setup-dominated** (a large count of setup-violated endpoints
at negative clock slack — a design far from setup closure) or **hold-dominated**
(many hold endpoints → many hold buffers), and the two want completely different
fixes. A hold-side fix does not touch a setup-dominated grind, and vice versa.

Before trusting any grt result about repair, always:

1. **Confirm `repair_timing` actually ran** — grep the log for `repair_timing`,
   `RSZ-` messages, and `Took N seconds: repair_timing`. If absent, a `SKIP_*`
   flag routed around it (Trap 1).
2. **Split setup vs hold** — read the setup-violated vs hold-violated endpoint
   counts and the setup- vs hold-buffer counts from the RSZ messages. Attribute
   the runtime to whichever dominates.
3. **Reconcile your hypothesis against the split.** If you framed the problem as
   a "hold pathology" but the measured grind is setup, the framing is wrong —
   fix the attribution before proposing a hold fix.

## Note on the effort dial

`repair_timing -effort low|medium|high` instruments the **setup** phase's
marginal-progress stop (it bails out of a non-convergent setup grind early). It
does not currently have an equivalent knob for the hold phase, and hold repair
is generally harder to bound than setup — so do not expect `-effort low` to
shorten a hold-dominated grind. See the deps-preflight skill for confirming
which effort actually reaches the tool.

Pairs with `byo-openroad` (iterate on a repair change) and `orfs-deps-preflight`
(validate the code path before the hours-long run).
