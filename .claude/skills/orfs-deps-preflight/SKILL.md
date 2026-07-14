---
name: orfs-deps-preflight
description: Pre-flight an hours-long ORFS _deps / make-extract stage run (grt, place, route, SAIF) by dumping the stage's effective variables and mentally dry-running the flow TCL to confirm the code path you are testing will actually execute. Use before committing to any long OpenROAD flow-stage run, especially when a SKIP_* flag, an *_EFFORT setting, or a setup/hold selector could silently route around what you intend to measure.
---

## Goal

Never discover *after* an hours-long run that a `SKIP_*` flag or a helper default
routed around the exact code path you were trying to exercise. Spend a few
minutes up front proving the run will hit it.

## The core move: mentally dry-run the flow TCL

ORFS flow scripts read only a handful of env vars — stepping through
`global_route.tcl` / `util.tcl` (or the relevant stage script) by hand is quick.
Trace which vars gate your target code path, plug in your intended settings, and
**predict the exact command the run will emit** and whether your path executes.
If the prediction is wrong, adjust the invocation **before** launching. This is
minutes of reading that saves hours of runtime.

## Know how each var reaches the tool — cmdline vs export

This is the subtlety that bites: a `make` command-line variable does **not**
reach openroad's process env unless the Makefile explicitly `export`s it (make
does not auto-export cmdline vars).

- A var the stage's `args.mk` marks `export` **does** propagate when you override
  it on the make command line (e.g. `SKIP_INCREMENTAL_REPAIR=...`).
- A var that is only read from the TCL's `::env(...)` but is **not** exported by
  the flow **will not** see your make-cmdline override — you must pass it as a
  real exported ENV var.

Worked example of the failure mode: a repair helper selects `-setup` vs `-hold`
from `::env(REPAIR_SETUP_ONLY)`, defaulting to setup-only unless it equals `0`.
If that var is neither in the `args.mk` nor blanket-exported, a make-cmdline
`REPAIR_SETUP_ONLY=0` never reaches openroad → the run silently does setup-only
and tests nothing about hold. The fix is to export it as an ENV var, not pass it
on the make line.

## The pre-flight checklist

1. **Dump the stage's effective vars.** Grep the stage `*.args.mk` (e.g.
   `<stage>.args.mk`) for the gating vars — `SKIP_*`, `*_EFFORT`,
   `*_SLACK_MARGIN`, setup/hold selectors — and note your command-line
   overrides, remembering cmdline beats `?=`/`export` **only for exported vars**.
2. **Read the flow TCL to see how those vars gate your target.** e.g.
   `global_route.tcl`'s `if { !$SKIP_INCREMENTAL_REPAIR } { ... repair_timing_helper }`,
   and the helper's `-setup`/`-hold`/`-effort` logic. Write down the exact
   command your run should emit (the flow echoes it back).
3. **Prove the path fires.** Once running, check the log for the invocation and
   its markers before trusting the result (e.g. `repair_timing`, the RSZ hold-
   endpoint / hold-buffer messages, `Took N seconds: <command>`). If a phase is
   absent, a flag routed around it — stop and fix the invocation.
4. **Only then commit to the hours-long run.**

## Not every log tag matches the stage name

OpenROAD passes call into each other's code, so a stage log naturally interleaves
message tags from other modules — e.g. a global-route (`grt`) run emits
detailed-router (`DRT-*`) messages during `pin_access`, which is drt code that
grt pulls on as slow prep *before* `repair_timing`. Seeing another module's tag
is not evidence of a mis-run stage; check the actual command sequence, not the
tag prefixes.

Pairs with `repair-timing-grt` (a skip-repair grt measures nothing about repair)
and `byo-openroad`.
