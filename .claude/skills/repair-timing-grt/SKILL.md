---
name: repair-timing-grt
description: Investigate OpenROAD global-route repair_timing correctly — the grt "grind"/timeout, hold- and setup-buffer insertion. Covers why a skip-repair (fast) grt measures nothing about repair, why repair_timing must run inside global_route.tcl on the pre-GR ODB, and how to split the grind into setup vs hold before blaming either. Use when a grt stage times out or runs for hours, when a change is meant to affect repair_timing, or when reasoning about hold vs setup buffer insertion at global route.
---

## Goal

Get a *trustworthy* answer about `repair_timing` at global route: whether it
grinds, why, and whether a proposed change moves it. Three traps below have each
wasted hours-long runs; avoid all three before drawing any conclusion.

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

## Trap 3 — split the grind into setup vs hold before blaming either

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
