# flush_pipe: the rung between lint and the overnight run

Status: **proposed, not built.** The two mechanisms it needs already
exist in this repo and are demonstrated by shipped features; the one
thing missing is on the ORFS side and is about six lines. A cheaper
finding fell out of writing this down and should be done first: the lint
rung is already built here and is wired up by no ORFS design at all.

## The question

> Just run through the flow and tell me what problems you see
> downstream, don't fuss over QoR -- we'll run overnight later.

The default posture of the flow is tapeout or bust: every stage tries to
converge, and a stage that cannot converge stops the flow. `ideas/eta.md`
put it the same way from the other direction -- for design-space
exploration that is the wrong trade.

What the question wants is a run that reaches `final` carrying whatever
it managed, so the *downstream* problems become visible in one pass:
congestion, unroutable pins, antenna divergence, DRC classes, a missing
via rule. QoR is explicitly not the deliverable. The overnight run is.

## What this is not: a timeout, an interrupt, or a forecast

Three plausible-looking mechanisms are all wrong, and two of them are
already settled.

**Not a forecast.** `ideas/eta.md` measured this and left a moratorium:
forecasting time-to-completion from ORFS progress logs does not beat the
base rate on the decision it exists to inform. Nothing here re-opens it.
The surviving idea there -- a plateau stop rule feeding
`REPAIR_TIMING_MAX_PASSES` and friends -- is this document's sibling, and
the two compose (see below).

**Not an interrupt**, although OpenROAD has one and it is better built
than one would guess. `utl::Progress` installs a SIGINT handler with
escalation (`src/utl/src/Progress.cpp:25`, `:72`) and the GUI has a stop
button (`src/gui/src/GUIProgress.h:114`). It is deliberately scoped in
two ways:

* Interrupting where the database is dirty is a hard error, UTL-0013,
  "may have modified the database" (`src/utl/src/Progress.cpp:246`). An
  interrupt is only legal at a boundary the algorithm declares safe.
* Consequently there is exactly **one** call site in the whole OpenROAD
  tree: detailed routing's outer iteration loop
  (`src/drt/src/dr/FlexDR.cpp:2139`), where each iteration ends with a
  legal database. `repair_timing` has no such exposed boundary.

And it is switched off precisely where a flow runs: `setBatchMode()`
(`src/OpenRoad.cc:211`) is fed from the `-exit` flag
(`src/Main.cc:282`), which every bazel-orfs action uses.

**Not a signal**, under bazel especially. There is no stable PID through
the sandbox, SIGINT belongs to bazel's own cancellation, a handler can
only set the atomic flag `Progress` already sets, and -- the real
objection -- a truncated output caches under an unchanged action key and
is silently reused forever.

The conclusion all three arrive at: **the budget has to be an a priori
input to the action key.** Wall-clock never can be. A fixed budget is
deterministic, cacheable and reproducible, and it needs no new
machinery in OpenROAD at all.

## The ladder

| Rung | Mechanism | Cost | Answers |
|---|---|---|---|
| 0 | analysis-time checks | free | are the variables and stage wiring real? |
| 1 | `variant="lint"`, mock-openroad | seconds | does the flow *run*? |
| 2 | **`flush_pipe`** (proposed) | minutes | does the design *survive*? |
| 3 | full flow | overnight | QoR |

Rung 0 is `check_stage_variables` (`private/stages.bzl:253`) spell-checking
every key against `variables.yaml`, `check_user_stages` (`:389`) policing
the `user_arguments`/`user_sources` escape hatches, and the hard fails in
`orfs_flow` for `data =` fan-out and `abstract_stage` with `last_stage`.
No action executes.

## Rung 1 exists here and is wired up by nobody

`orfs_design(mock_openroad = ...)` generates a whole second flow at
`variant="lint"` (`private/orfs_design.bzl:307-324`), and it is stronger
than the name suggests: `mock-openroad` is a ~1900-line Tcl interpreter
(`mock/openroad/src/bin/tcl_interpreter.py`) describing itself as an
"estimation engine for ORFS flows". It *executes every ORFS Tcl script
end to end* -- real control flow, real variable reads, real `source` of
the design's own hooks -- with estimated results instead of real
placement and routing. `sweep.bzl:71-84` already accepts `"lint"` as a
sweep variant.

The generation is guarded: `if mock_openroad:` (`orfs_design.bzl:308`).
ORFS's own `flow/designs/design.bzl` never passes it, and a grep over all
173 design `BUILD` files in `flow/designs/` finds zero occurrences. **No
ORFS design has lint targets today.**

Wiring that is one kwarg and is by some distance the cheapest item in
this document. It also catches the failure mode an agent iterating on a
`config.mk` or a `BUILD` file actually produces -- a typo'd variable, an
unsourced hook, a path that does not resolve -- which `flush_pipe` would
reach far more slowly.

Do rung 1 first.

## What rung 1 cannot answer

One line draws the boundary:

```python
if save_odb and not kwargs.get("lint"):     # private/flow.bzl:765
```

The lint flow deliberately produces **no ODB**. It estimates; it cannot
tell you that a macro placement makes routing impossible. So:

* **Lint** answers *does the flow run?* -- variables, script wiring,
  missing sources, Make expansion.
* **flush_pipe** answers *does the design survive?* -- the physical
  reality that only real tools see.

They are complementary, not redundant.

## flush_pipe, in bazel-orfs

Both halves of the pattern already ship here.

**The argument shape is `quick_pins`.** `private/flow.bzl:385` takes a
bool and the implementation (`:475-479`) is a `sources |` injection. Its
docstring (`:465-469`) reads *"Trades suboptimal pin placement for a
large wall-time saving... Suitable for RTL exploration; not for
tape-out."* `quick_pins.tcl:1` calls itself *"a cheap pin-placement
shortcut for exploration flows."* `flush_pipe` is its sibling, aimed at
effort knobs rather than pin placement.

**The isolation shape is `mock_area`.** Degraded runs already get their
own output namespace by variant suffixing:

```python
def _variant_name(variant, suffix):              # private/flow.bzl:353
    return "_".join([part for part in [variant, suffix] if part])

abstract_variant = _variant_name(variant, "unmocked" if mock_area else None)
```

That is the whole of the cache-safety and golden-safety requirement,
already solved. `flush_pipe` reuses it verbatim, which also gives
separate `FLOW_VARIANT` output paths in ORFS (`flow/Makefile:103-109`).

Sketch:

```python
if flush_pipe:
    arguments = arguments | {
        "CONTINUE_ON_GATE_FAILURE": "1",
        "DETAILED_ROUTE_END_ITERATION": "5",
        "SKIP_CTS_REPAIR_TIMING": "1",
        "SKIP_INCREMENTAL_REPAIR": "1",
        "GPL_TIMING_DRIVEN": "0",
        "GPL_ROUTING_DRIVEN": "0",
    }
    variant = _variant_name(variant, "flush")
```

That knob list is lifted almost verbatim from ORFS's own
`flow/designs/asap7/minimal/config.mk`, which carries the comment
*"Faster build, remove these in your own config.mk."* The argument would
be promoting an existing hand-rolled idiom into a named one.

**Use `DETAILED_ROUTE_END_ITERATION`, not `DETAILED_ROUTE_ARGS`.** The
latter *replaces* the entire argument list (the ternary at
`flow/scripts/detail_route.tcl:35`) and silently drops
`-db_process_node`, `OR_SEED`, `OR_K`, the via-in-pin layers,
`-repair_pdn_vias` and `-drc_report_iter_step 5`. The former goes through
`append_env_var` (`:22`) and composes. A flush run must differ from the
overnight run in *effort only*; a run that also differs in process setup
answers a question nobody asked.

## What has to change in ORFS

No bazel-side argument demotes a Tcl `error`. These are the gates that
end a low-effort run:

| Gate | Location |
|---|---|
| `error "Design has unrouted nets."` | `flow/scripts/detail_route.tcl:76` |
| `error "Global routing failed..."` | `flow/scripts/detail_route.tcl:5` |
| `error "Detailed placement failed in CTS: $msg"` | `flow/scripts/cts.tcl:52`, `:77` |
| `utl::error GPL 200` | `flow/scripts/global_place.tcl:44` |
| `error "Repair timing output failed lec test"` | `flow/scripts/lec_check.tcl:72` |

The detailed-route one is the load-bearing case and is worse than it
looks. `orfs_write_db .../5_2_route.odb` sits at `detail_route.tcl:84`,
*after* the error at `:76`. A run with a low `-droute_end_iter` will
leave unrouted nets by construction, abort, and write **no ODB** -- so
bazel gets no declared output, no downstream stage runs, and the
artifact you wanted to inspect does not exist. The failure is not merely
early, it is non-productive.

The change is an ORFS variable, say `CONTINUE_ON_GATE_FAILURE`, that
turns those `error`s into `utl::warn` plus a metric and lets the stage
write its ODB anyway. Roughly six sites.

Per the upstream moratorium in `CLAUDE.md`, that ships **here, as a
carried patch** -- `patches/00NN-orfs-flush-pipe-gates.patch` listed in
`ORFS_PATCHES` (`orfs_source.bzl:53`) -- not as an upstream pull request.
The header says what it fixes, that it is not upstreamed, and that it
retires on a `//:bump` onto an ORFS that carries the change. Putting the
demotion in ORFS rather than in Starlark also means Make users get the
same mode, and the definition of "what is a gate" stays next to the
gates.

Division of labour: bazel-orfs owns *how hard do we try* (the knobs and
the variant), ORFS owns *what is fatal* (the gates). That is the same
split `quick_pins` uses -- exploration policy here, hook points there.

## Relationship to ideas/eta.md

`eta.md` killed forecasting and kept a plateau stop rule: *halt when TNS
has not improved by more than X% over the last N passes*, which it called
"the anti-futility knob the original proposal wanted, arrived at from the
other end."

That rule is **adaptive**: it measures, then stops. `flush_pipe` is the
**a priori** cousin: it fixes the budget before the run and measures
nothing. They compose cleanly -- `flush_pipe` sets a deliberately small
budget, and a plateau rule would stop earlier still on runs where even
that budget is generous. Neither forecasts anything, so the moratorium
is intact.

One incidental benefit: flush runs are cheap same-design sibling runs,
which is condition 2 of eta.md's list of things that would re-open its
verdict.

## Open questions

1. **Which gates are genuinely safe to demote?** "Unrouted nets" is the
   obvious one, but `final_outputs`, GDS write and LEC all consume that
   result. The honest answer may be that flush implies a `last_stage`
   short of GDS, which would weaken the "run through the whole flow"
   promise. Needs a real run to settle.
2. **Can a flush ODB be consumed as a macro abstract by another design?**
   Variant isolation should prevent it. Worth an explicit test rather
   than an assumption, because the failure would be silent and would look
   like a QoR regression in the parent.
3. **What exactly gets stamped in the metrics?** Every demoted gate needs
   to appear, so that nothing downstream -- a golden comparison, a
   pareto check, a sweep scorer -- can mistake a flush run for a complete
   one. This is the requirement the variant suffix enforces structurally;
   the metrics record is what makes it legible to a human reading a
   report.
4. **Does `flush_pipe` want `quick_pins` implied?** They target the same
   user and the same trade. Composing them is free; making one imply the
   other is a policy call.

## Proposed order

1. Wire `mock_openroad`/`mock_yosys` through ORFS's `design.bzl` so rung
   1 exists for real designs. Cheapest, largest immediate return,
   independent of everything below.
2. Carry the ORFS gate-demotion patch. Nothing about `flush_pipe` works
   without it.
3. Add `flush_pipe` to `orfs_flow`, following `quick_pins` for the
   argument and `mock_area` for the variant.
4. Only then consider the adaptive plateau rule from `eta.md`, which is a
   refinement of step 3 and not a prerequisite for it.
