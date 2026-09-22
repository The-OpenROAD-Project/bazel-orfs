# flush_pipe: a default, not a variant

Status: **proposed, not built.** The ORFS-side change is about six
sites plus a reader; the bazel-orfs side is a default and a flag.

The document's own first draft got the shape wrong in an instructive
way, and the correction is the most useful thing in it. That draft
proposed `flush_pipe` as a new flow variant and opened its plan with
"wire up the lint rung". Both were the same mistake, and there is a
measurement sitting in the repo that says so: the lint rung is a good
capability, written by this repo's own authors, at **173 designs, zero
adoptions** (`flow/designs/`). It shipped as a new flow variant, and a
new flow variant is a parallel set of targets that nobody builds.
Wiring it up harder would repeat the mistake rather than fix it.

So the design rule this document ends up asserting is narrower and more
useful than the one it started with:

> **No new variant, no new targets.** A mode that needs a user to build
> something they would not otherwise have built has already lost.

`flush_pipe = True` as the **default**, with `False` for anyone who
wants today's fail-at-the-first-gate behaviour. When a stage is
hopeless it records that in its own declared output, the action
*succeeds*, and the next stage reads the marker and flushes in turn. The
target graph does not change at all. This is deterministic by
construction, for the reason given in *How the marker makes it
deterministic* below.

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

The shape of the work matters. This is the posture of someone who has
just changed something structural -- a floorplan, a macro placement, a
new block, a PDK bump -- and wants to know whether the change is viable
at all before committing a night to it. The failure they are hunting is
categorical, not marginal: *this does not route*, not *this routes 3%
worse*. A single run that surfaces four such problems at once is worth
more than four clean runs that each stop at the first one, because the
expensive resource being spent is not CPU, it is the human's round
trips.

That framing is also what makes the tapeout-or-bust default actively
harmful here rather than merely conservative. A flow that stops at the
first gate converts a four-problem run into four sequential runs, and
each round trip costs more than the compute it saves.

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

| Rung | Mechanism | Cost | Answers | Reached by |
|---|---|---|---|---|
| 0 | analysis-time checks | free | are the variables and stage wiring real? | every build |
| 1 | `variant="lint"`, mock-openroad | seconds | does the flow *run*? | **nobody** |
| 2 | **`flush_pipe`** (proposed) | full run | does the design *survive*? | every build, by default |
| 3 | full flow | overnight | QoR | every build |

The last column is the one that matters, and it is why rung 1 is
evidence rather than a recommendation. Rungs 0 and 3 are reached because
they are what happens when you type the ordinary command. Rung 1 is
reached by nobody because it is not. The proposal for rung 2 is shaped
to land in the first column, not the second -- which is also why it does
not save wall-clock on its own: flushing changes what a failing run
*produces*, not how long it takes. The budget flag is the separate thing
that buys time.

Rung 0 is `check_stage_variables` (`private/stages.bzl:253`) spell-checking
every key against `variables.yaml`, `check_user_stages` (`:389`) policing
the `user_arguments`/`user_sources` escape hatches, and the hard fails in
`orfs_flow` for `data =` fan-out and `abstract_stage` with `last_stage`.
No action executes.

## The lint rung, and why it is evidence rather than a to-do

The capability is real and is better than its name. `mock-openroad` is a
~1900-line Tcl interpreter (`mock/openroad/src/bin/tcl_interpreter.py`)
describing itself as an "estimation engine for ORFS flows". It
*executes every ORFS Tcl script end to end* -- real control flow, real
variable reads, real `source` of the design's own hooks -- with
estimated results instead of real placement and routing. It would catch
exactly what iterating on a `config.mk` produces: a typo'd variable, an
unsourced hook, a path that does not resolve.

It is also shipped in the shape that guarantees nobody uses it.
`orfs_design(mock_openroad = ...)` generates *a whole second flow* at
`variant="lint"` (`private/orfs_design.bzl:307-324`), guarded by
`if mock_openroad:` (`:308`). ORFS's own `flow/designs/design.bzl` never
passes it, and a grep over all 173 design `BUILD` files under
`flow/designs/` finds zero occurrences.

**That is the measurement.** A good capability, in a repo whose authors
wrote it, at zero adoption, because using it requires knowing it exists
and then building targets you would otherwise never build. The right
conclusion is not "wire it up harder":

> A new flow variant is a parallel set of targets that nobody builds.
> Whatever else a mode does, it must not require one.

The first draft of this document proposed `flush_pipe` as a variant and
put "wire up lint" at the top of its plan. Both were the same mistake.
The rest of the document is what survives applying the rule to itself.

The useful thing to take from lint is not its targets but its estimation
engine: a mode that flushes the pipe has to do *something* cheap in place
of the work it is skipping, and there is a working estimator in this repo
already.

## Cognitive load is the constraint, not capability

The lint flow is not missing. It is *invisible*, and it was invisible to
the people who wrote it -- this document was drafted by someone who had
forgotten the feature existed. That is the finding, and it generalises:
**a rung nobody reaches for returns nothing, however well it works.**

The invisibility is structural rather than a memory failure. Lint
targets do not exist until you pass `mock_openroad`
(`orfs_design.bzl:308`); `_html` targets do not exist until you pass
`html = True` (`flow.bzl:464`, default `False`). A user who does not
already know the feature exists therefore cannot discover it -- not by
`bazel query`, not by tab completion, not by reading the target list.
The kwarg gates the *existence* of the thing that would have advertised
it.

Adding `flush_pipe = False` as a fifth such kwarg would reproduce the
defect exactly. If the answer to "why did nobody use lint" is "they
forgot", then the answer to "why did nobody use flush_pipe" will be the
same, and the feature will have cost more than it returned.

### The default is the answer, and it needs the proposal split in two

The best fix for "nobody reaches for the tool" is that **nobody has to**:
make flushing the default, and let `orfs_flow(flush_pipe = False)` turn
it off. No target to discover, no kwarg to remember, no failure message
to read. That is a strictly better answer than anything in the two
subsections below, and it is available only because the mode is *static*
-- fixed before the run, identical on every run, an ordinary input like
any other.

That requires separating two things this document had bundled, and the
bundle was the error:

| | What it changes | Safe as a default? |
|---|---|---|
| **Gate behaviour** | a failing stage warns, records a metric and writes its ODB instead of aborting | **yes** |
| **Effort budget** | `-droute_end_iter 5`, the `SKIP_*` set, reduced repair passes | **no** |

Only the first belongs on by default. Defaulting the second would mean
nobody ever gets a real result, which is the opposite of the goal. So
`flush_pipe = True` should mean *"do not stop at the first gate"* and
nothing else; the budget stays an explicit, separate opt-in for the
person who actually wants a fast recon pass.

With that split the default is easy to justify. Full effort, unchanged
QoR, same runtime -- but a run that dies in detailed routing now also
tells you what `final`, GDS and LEC would have said, in the same pass.
The four-problems-in-one-run property from *The question* becomes the
default posture rather than an opt-in mode, and tapeout-or-bust becomes
the thing you ask for.

### How the marker makes it deterministic

The mechanism is the part that makes the default safe, and it needs no
new target, no variant and no coordination between stages.

When a stage finds itself in a hopeless state, it **writes that into its
own declared output** -- the ODB, or a sidecar the stage already
produces -- naming the gate that fired and why. Then the action
*succeeds*. The next stage reads its input, sees the marker, and flushes
in turn: it does not attempt real work on a result that cannot support
it, it does the cheap thing, propagates the marker and keeps going. The
marker reaches the last stage, which reports the whole chain at once.

Determinism is not something this has to be argued into; it falls out of
where the marker lives:

* The marker is **in the data**, so it is part of the output's content
  hash, so it is part of every downstream action's key. A degraded route
  result and a clean one are different inputs and cache as different
  entries. There is no path by which a flushed artifact is reused as a
  clean one.
* Every stage's behaviour is a **pure function of its inputs**, exactly
  as before. Nothing is decided by observing wall-clock, load or
  progress across an action boundary.
* "Hopeless" has to be a **deterministic predicate on design state** --
  *N nets still unrouted after the configured iterations*, not *this is
  taking a while*. Same design, same configuration, same verdict, every
  time, on any machine.

This is also what makes a false green impossible rather than merely
unlikely. The earlier draft proposed a terminal check that failed the
last target if any gate had fired; the marker subsumes it, because the
distinction between a degraded artifact and a clean one is carried by
the artifact instead of by a naming convention or a separate audit. The
last stage still decides whether a marked run exits red -- and it should
-- but nothing depends on that decision for correctness.

It disposes of *Open question 2* as well: a flushed ODB cannot be
silently consumed as a macro abstract by a parent design, because the
parent's action sees different input bytes and the marker travels with
them.

### What is still rejected: switching at runtime

The distinction that matters is *when the decision is made*, not what it
decides.

**Rejected** -- a stage observing its own progress and deciding
mid-action to give up and flush. The output would depend on something
not in the action key: not reproducible, not safely cacheable, and a
truncated ODB gets reused forever. This is the wall-clock idea wearing a
different hat, and the reasons in *What this is not* apply unchanged.

**Fine** -- flushing as a configured default, resolved before the run
starts. Every run behaves identically, the setting is an ordinary input,
and nothing is decided by observation. The objection above simply does
not reach it.

**Not available either way** -- bazel noticing a target failed and
building a different variant instead. Conditional-on-failure edges would
make the graph nondeterministic, so bazel cannot express it. If a
one-command escalation is wanted later, it has to be a `bazel run`
wrapper that invokes bazel twice, with the decision in a script outside
the actions. With the default flipped, there is not much left for it to
do.

### The budget half is a flag, not a variant

The same rule applies to the half that stays opt-in. A macro argument
that produces different QoR needs somewhere for the different result to
live, and the first draft reached for a variant suffix -- which is the
shape lint proved does not get used.

This repo already has the right mechanism, and uses it for exactly this
kind of thing:

```python
# BUILD:63, and see the comment above it
orfs_bool_flag(
    name = "log_timestamps",
    build_setting_default = False,
    visibility = ["//visibility:public"],
)
```

`--@bazel-orfs//:log_timestamps` changes what every ORFS action does
without adding a single target, and its own comment states the cache
semantics that make it safe: *"Stamping changes the log bytes, so a
stamped run does not share cache entries with an unstamped one and
turning it on costs a rebuild of the stages you ask for."* `eta.md`
describes it as "an additive debug flag ... shipped separately as a
feature in its own right".

The effort budget should be exactly that:

```sh
bazelisk build --@bazel-orfs//:recon //flow/designs/asap7/gcd:gcd_final
```

Same target, same label, different configuration. Nothing to discover in
a target list, nothing to name, and the artifacts separate themselves by
configuration the way `log_timestamps` already does. The `recon` name is
a placeholder; what matters is the shape.

### What this implies for the proposal

The document was drafted as "add a knob, and a variant to put it in".
Applying the rule the lint measurement establishes leaves neither:

* the gate behaviour is a **default**, so there is nothing to discover;
* the budget is a **flag**, so there is nothing to build that did not
  already exist;
* the degraded-versus-clean distinction rides in the **artifact**, so
  there is nothing to audit and no naming convention to trust.

Discoverability is not polish to be done after a feature lands. On this
evidence it decides whether the feature returns anything at all, and its
cheapest form is not a signpost pointing at a new target -- it is not
having a new target.

## What lint could not have answered anyway

Even wired up, lint would not have covered this use case. One line draws
the boundary:

```python
if save_odb and not kwargs.get("lint"):     # private/flow.bzl:765
```

The lint flow deliberately produces **no ODB**. It estimates; it cannot
tell you that a macro placement makes routing impossible.

* **Lint** answers *does the flow run?* -- variables, script wiring,
  missing sources, Make expansion.
* **flush_pipe** answers *does the design survive?* -- the physical
  reality that only real tools see.

So the two are complementary in principle. In practice only one of them
is on a path a user actually walks, and the proposal here is to keep it
that way by construction rather than by exhortation.

## flush_pipe, in bazel-orfs

Both halves of the pattern already ship here.

**The argument shape is `quick_pins`.** `private/flow.bzl:385` takes a
bool and the implementation (`:475-479`) is a `sources |` injection. Its
docstring (`:465-469`) reads *"Trades suboptimal pin placement for a
large wall-time saving... Suitable for RTL exploration; not for
tape-out."* `quick_pins.tcl:1` calls itself *"a cheap pin-placement
shortcut for exploration flows."* `flush_pipe` is its sibling, aimed at
effort knobs rather than pin placement.

**The isolation shape is *not* `mock_area`.** `mock_area` gives degraded
runs their own output namespace by variant suffixing
(`_variant_name`, `private/flow.bzl:353`), and the first draft proposed
copying it. On the lint measurement that is the wrong model to copy: it
is correct, and it produces targets nobody builds. Isolation here comes
from the marker in the artifact instead, which costs no targets at all.

Sketch:

```python
def orfs_flow(..., flush_pipe = True, ...):
    # Gate behaviour. Default on. No variant, no new target: the
    # degraded-versus-clean distinction rides in the output bytes.
    if flush_pipe:
        arguments = arguments | {"CONTINUE_ON_GATE_FAILURE": "1"}
```

and the budget as a flag beside `log_timestamps`, read in
`private/environment.bzl` the way `log_timestamps_enabled(ctx)` is
(`:142`), rather than as a macro argument:

```python
orfs_bool_flag(
    name = "recon",
    build_setting_default = False,
    visibility = ["//visibility:public"],
)
```

whose payload is the knob set lifted almost verbatim from ORFS's own
`flow/designs/asap7/minimal/config.mk` -- `DETAILED_ROUTE_END_ITERATION`,
`SKIP_CTS_REPAIR_TIMING`, `SKIP_INCREMENTAL_REPAIR`, `GPL_TIMING_DRIVEN`,
`GPL_ROUTING_DRIVEN` -- a file that carries the comment *"Faster build,
remove these in your own config.mk."* The flag would be promoting an
existing hand-rolled idiom into a named one.

Names are open. `recon` keeps the two ideas visibly distinct on the
page; something reading better next to `log_timestamps` is fine.

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
turns those `error`s into `utl::warn`, **records the fired gate in the
stage's own output**, and lets the stage write its ODB anyway. Roughly
six sites, plus the marker's reader on the consuming side.

The marker is the part that does the work, not the warning. A warning
scrolls past and is gone; a marker in the artifact is what the next
stage keys on, what makes the degraded result cache separately from a
clean one, and what a reader of `6_final` can still see hours later.

Per the upstream moratorium in `CLAUDE.md`, that ships **here, as a
carried patch** -- `patches/00NN-orfs-flush-pipe-gates.patch` listed in
`ORFS_PATCHES` (`orfs_source.bzl:53`) -- not as an upstream pull request.
The header says what it fixes, that it is not upstreamed, and that it
retires on a `//:bump` onto an ORFS that carries the change. Putting the
demotion in ORFS rather than in Starlark also means Make users get the
same mode, and the definition of "what is a gate" stays next to the
gates.

Division of labour: bazel-orfs owns *how hard do we try* (the default
and the budget flag), ORFS owns *what is fatal* and *what gets recorded*
(the gates and the marker). Neither owns a variant, which is the point.

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
2. **Where exactly does the marker live?** Inside the ODB, or in a
   sidecar among the stage's declared outputs? The ODB keeps it
   inseparable from the artifact, which is the whole point, but costs a
   schema decision and an ORFS-side reader in every consuming stage. A
   sidecar is far easier and can be dropped or ignored, which is the
   failure mode the design exists to prevent. This is the main
   implementation question.
3. **What does a downstream stage actually *do* when it sees a marker?**
   "Do the cheap thing and propagate" is under-specified per stage, and
   getting it wrong wastes the run. The lint rung's estimator is the
   obvious source of cheap answers and is already in this repo.
4. **Does a marked run exit red, and where?** Correctness does not
   depend on it -- the marker already prevents a clean artifact being
   confused for a degraded one -- but a human wants a red build and a CI
   matrix needs one. Probably the last stage; needs stating.
5. **Can a degraded ODB be consumed as a macro abstract by a parent
   design?** The marker should make this structurally impossible, since
   the parent's action sees different input bytes. Worth an explicit
   test rather than an assumption, because the failure would be silent
   and would look like a QoR regression in the parent.
6. **Does the default change CI cost?** A flow that no longer stops at
   the first gate runs every remaining stage on designs that used to
   abort early. For a broken design that is precisely the point; across
   a CI matrix it is compute nobody asked for. `flush_pipe = False` in
   CI is the obvious answer, and worth stating deliberately rather than
   discovering from a bill.
7. **Does the budget flag want `quick_pins` implied?** They target the
   same user and the same trade. Composing them is free; making one
   imply the other is a policy call.

## Proposed order

The first draft opened this list with "wire up lint". That is struck:
wiring a variant up more firmly does not fix a variant.

1. Carry the ORFS gate-demotion patch: each gate records a marker in the
   stage's output and the stage writes its ODB instead of aborting.
   Nothing else here works without it.
2. Teach the consuming stages to read the marker and flush in turn.
   Question 3 is the real content of this step, and it is where the lint
   estimator earns its keep.
3. Flip `flush_pipe` on by default in `orfs_flow`. It is a two-line
   macro change once 1 and 2 exist; the work is all upstream of it.
4. Add the budget as an `orfs_bool_flag` beside `log_timestamps`. No
   variant, no new targets, no macro argument.
5. Only then consider the adaptive plateau rule from `eta.md`, which
   refines step 4 and is not a prerequisite for any of it.

Lint is not on this list. Its estimator is used by step 2; its targets
are the thing this document is arguing against.
