# flush_pipe: the rung between lint and the overnight run

Status: **proposed, not built.** The two mechanisms it needs already
exist in this repo and are demonstrated by shipped features; the one
thing missing is on the ORFS side and is about six lines. A cheaper
finding fell out of writing this down and should be done first: the lint
rung is already built here and is wired up by no ORFS design at all.

**And that finding turns out to be the more important half of the
document.** A rung nobody reaches for is worth nothing even when it
works perfectly. The lint flow works and was forgotten by the people who
built it. Adding a fifth knob to a repo whose fourth knob is invisible
does not obviously help, so the design question is not "what should
`flush_pipe` do" but "how does a user end up on the right rung without
having to remember that the rung exists".

The answer that survived is that **flushing should be the default** --
`orfs_flow(flush_pipe = True)`, with `False` available to anyone who
wants today's fail-at-the-first-gate behaviour. That works only once the
proposal is split in two: gate behaviour defaults on, the effort budget
stays opt-in. See *Cognitive load is the constraint*; it reorders the
whole document.

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

**It must not produce a false green.** If stages succeed with degraded
artifacts, a plain `bazel build //design:gcd_final` could hand back a GDS
built from an unrouted design. The fix is to let the flow run to the end
and fail at the end: each stage records its fired gates as a metric, and
the terminal stage fails if any gate fired anywhere upstream. Every
intermediate stage succeeds, so every downstream stage runs and every
report gets written; the terminal target still goes red, so nothing
mistakes the result for a good one. Bazel caches the stages that
succeeded, and only the cheap terminal check re-runs.

That also disposes of most of *Open question 2* -- a flush artifact
cannot be silently consumed as a macro abstract by a parent design if
the target that produces it never goes green.

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

### Make the targets exist

`tags = ["manual"]` is already the repo's answer to "generate it always,
never build it by accident" -- used at `flow.bzl:187`, `:256`, `:264`,
and described at `:234` as keeping wildcard builds from failing. Applied
to the rungs, it means `bazel query //flow/designs/asap7/gcd:*` lists the
lint and flush targets, tab completion offers them, and `//...` still
does not pay for them.

That is the whole fix for "the feature does not exist until you know it
exists": generate the rungs unconditionally and let the tag carry the
cost control. The kwarg becomes an override, not a gate.

The cost to weigh is analysis time, not build time. Generating a second
and third flow for each of 173 designs multiplies the target count, and
`manual` suppresses building but not analysis. That number should be
measured before this is adopted, not assumed -- it is the one thing that
could sink the approach.

### Make the failure point at the next rung

The highest-leverage fix is also the smallest, and ORFS already does it
elsewhere:

```tcl
error "Global routing failed, run `make gui_grt` and load ...
                                       # flow/scripts/detail_route.tcl:6
puts "Run 'make gui_$stage.odb' to load progress snapshot"
                                       # flow/scripts/cts.tcl:13
```

A user reading a failure is, by definition, looking at the screen and
wanting a next step. That is the only moment a suggestion is certain to
be read, and it costs nothing to remember because it arrives exactly
when it is relevant. Every gate this document proposes to demote should
name the flush target in its message:

```
ERROR: design has unrouted nets after 5 iterations.
  To push the incomplete result through the remaining stages and see
  what else breaks:  bazel build //flow/designs/asap7/gcd:gcd_flush_final
```

With that in place, the `flush_pipe` kwarg is an implementation detail
rather than the product. **The product is the ladder announcing
itself.** A user who has never read this document, never heard of lint
and never seen `flush_pipe` still ends up on the right rung, because the
failure told them which one it was.

### What this implies for the proposal

The document was drafted as "add a knob". On the evidence above that is
the wrong emphasis, and the two subsections immediately above are what a
knob-shaped proposal needs to stay usable -- they are not what it needs
to be *right*.

Defaulting the gate behaviour does more than either of them, because it
removes the discovery step instead of shortening it. What survives of
the two is narrower and still worth doing:

* **Unconditional targets** still matter for the rungs that stay
  opt-in -- lint, and the effort budget -- since those keep the
  "invisible until you know" defect by construction.
* **Failure-time pointing** still matters, but points somewhere else
  once flushing is the default. The terminal gate check is the natural
  place: having listed the gates that fired, it is exactly where to name
  the budget target for a faster next iteration.

Discoverability is not polish to be done after the feature lands. On
this evidence it determines whether the feature returns anything at all,
and the cheapest form of it is not a signpost but a default.

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
already solved, and it gives separate `FLOW_VARIANT` output paths in ORFS
(`flow/Makefile:103-109`) for free.

It applies to the *budget* half only. A default-on gate-behaviour change
does not take a variant -- it does not alter QoR, so the result is still
the result, and suffixing every target in the repo to record a default
would be noise. What keeps that half honest is the terminal gate check
described above, not output isolation.

Sketch, with the split from *The default is the answer* respected --
two arguments, only one of them defaulted on, and only the one that
changes QoR taking a variant:

```python
def orfs_flow(..., flush_pipe = True, recon = False, ...):
    # Gate behaviour. Default on, no variant: QoR is unchanged, so the
    # result is the same result, and suffixing every target in the repo
    # to record a default would be absurd.
    if flush_pipe:
        arguments = arguments | {"CONTINUE_ON_GATE_FAILURE": "1"}

    # Effort budget. Opt-in, and it *does* take a variant, because the
    # QoR is deliberately not the real QoR.
    if recon:
        arguments = arguments | {
            "DETAILED_ROUTE_END_ITERATION": "5",
            "SKIP_CTS_REPAIR_TIMING": "1",
            "SKIP_INCREMENTAL_REPAIR": "1",
            "GPL_TIMING_DRIVEN": "0",
            "GPL_ROUTING_DRIVEN": "0",
        }
        variant = _variant_name(variant, "recon")
```

The budget list is lifted almost verbatim from ORFS's own
`flow/designs/asap7/minimal/config.mk`, which carries the comment
*"Faster build, remove these in your own config.mk."* That argument would
be promoting an existing hand-rolled idiom into a named one.

The naming is open. `recon` is used here only to keep the two ideas
visibly distinct on the page; `flush_pipe` plus `effort` or
`quick = True` may read better next to `quick_pins`.

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
2. **Where does the terminal gate check live, and what is it?** The
   no-false-green property rests entirely on it. A separate cheap action
   that reads the accumulated per-stage metrics is the obvious shape, but
   it has to see every stage a given target actually built, including
   `last_stage` and `abstract_stage` truncations, and it must not itself
   become a thing a target can be built without.
3. **Can a degraded ODB be consumed as a macro abstract by a parent
   design?** Largely answered by the terminal check -- a target that
   never goes green cannot be depended on -- but "largely" is not
   "demonstrably", and the failure would be silent and would look like a
   QoR regression in the parent. Worth an explicit test.
4. **What exactly gets stamped in the metrics?** Every fired gate needs
   to appear, so that nothing downstream -- a golden comparison, a
   pareto check, a sweep scorer -- can mistake a pushed-through run for a
   clean one. With the gate behaviour defaulted on, this record is the
   *only* structural distinction for the default path; the variant suffix
   protects the budget path alone.
5. **Does the default change CI cost?** A flow that no longer stops at
   the first gate runs every remaining stage on designs that used to
   abort early. For a broken design that is precisely the point; across a
   CI matrix it is compute nobody asked for. `flush_pipe = False` in CI
   is the obvious answer, and worth stating deliberately rather than
   discovering from a bill.
6. **Does the budget knob want `quick_pins` implied?** They target the
   same user and the same trade. Composing them is free; making one imply
   the other is a policy call.

## Proposed order

1. Wire `mock_openroad`/`mock_yosys` through ORFS's `design.bzl` so rung
   1 exists for real designs. Cheapest, largest immediate return,
   independent of everything below.
2. Carry the ORFS gate-demotion patch, with the metric each demoted gate
   records. Nothing else here works without it.
3. Add the terminal gate check. It has to land with, or before, the
   default flip -- a default that can produce a green build from an
   unrouted design is worse than no default at all.
4. Flip `flush_pipe` on by default in `orfs_flow`, following `quick_pins`
   for the argument shape.
5. Add the effort budget as its own opt-in argument, following
   `mock_area` for the variant, and generate its targets unconditionally
   under `tags = ["manual"]` so it does not inherit the invisibility this
   document is about.
6. Only then consider the adaptive plateau rule from `eta.md`, which
   refines step 5 and is not a prerequisite for any of it.
