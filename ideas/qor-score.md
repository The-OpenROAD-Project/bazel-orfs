# Scoring an OpenROAD pull request: a Pareto front and a design ledger

> **Status: idea, not a plan.** Written 2026-09-06 while scoring a single
> pull request by hand. Everything under "What was measured" is measured;
> everything under "The idea" is not built. The immediate work is scoring one
> pull request end to end, and this document exists so the larger shape is
> recorded rather than rebuilt from memory later.

## The problem

An OpenROAD pull request that changes QoR cannot easily be given an opinion.
The evidence a maintainer needs costs days of flow wrangling to produce, so
asking for it is close to equivalent to closing the pull request, and the
change either stalls or is merged on faith. Neither outcome tells anyone
whether the algorithm helps.

The existing answer is golden files. A change either leaves `.ok` files alone
or rebaselines them, which converts every quality trade into "the goldens
moved" -- a fact carrying no direction. A contributor who improves WNS at the
cost of area has no vocabulary to say so and no way to be believed.

### How often that happens

`docs/studies/pr-lifecycle/` measures it. The 120 most recently updated
OpenROAD pull requests in each state, bot-authored ones dropped, collected
2026-09-06; `collect.py` regenerates `data.json`.

| | merged | abandoned |
|---|---|---|
| pull requests in sample | 112 | 99 |
| inline review threads opened by bots | 248 | 431 |
| inline review threads opened by humans | 52 | 45 |
| bot share of review threads | 83% | 90% |
| **pull requests with zero human engagement** | **11%** | **30%** |
| commits after bot feedback, before any human | 40% | 36% |
| median days open | 0.96 | 9.24 |

Machines write most of the review, and the volume does not discriminate: the
abandoned population received *more* machine attention than the merged one and
*less* human attention. What separates them is whether any person said
anything at all, and there the gap is near enough three times. Merged pull
requests close in about a day; abandoned ones take nine, which is not a quick
no but a long silence.

This does not show the machine comments are wrong or trivial -- the automated
reviewer labels its own inline threads medium and above, and this did not
adjudicate them -- nor does it show causation. It shows that machine review is
most of the volume and does not predict the outcome, while sparse human review
does. A score exists to make the human half cheap enough to happen.

### What a stalled pull request looks like up close

OpenROAD PR 10662 adds a resizer move that replaces one buffer with a pair of
cascaded inverters. Its eight inline review threads, checked against the code
at its head commit rather than against the discussion:

| finding | source | severity | status at head |
|---|---|---|---|
| footprint filter rejects every inverter, disabling the move | bot | high | **live, unfixed** |
| `makeInstance` return values unchecked | bot | medium | fixed by the author |
| driver location ignored for block terminals | bot | medium | not applicable -- the code uses `dbNetwork::location()`, which resolves BTerms |
| load centroid excludes block terminals | bot | medium | not applicable -- same |
| move type naming | human | -- | fixed by the author |
| naming suggestion answered | human | -- | applied |
| `estimate()` not overridden, so the MT policy cannot rank the move | human | -- | live, deferred by the author |
| endorsement of the footprint finding | human | -- | -- |

Of the automated reviewer's four findings, one was real and important, one had
already been fixed, and two did not apply to the code as written. The real one
disables the move on an entire platform; a maintainer agreed in the thread
that the check should go; it is still there. The pull request was then marked
stale.

The question that would have unblocked it -- *"Do you have QoR results for the
public designs?"* -- is not among the inline threads at all. Nobody answered
it. That is the gap a score is for, and it is why the review being thorough
did not help.

## What was measured

These numbers come from an actual run, not an estimate. sky130hd/aes, 18383
instances, ~10 cores busy, forked at the seam `patches/0050` cuts between
global routing and incremental repair:

| phase | wall time |
|---|---|
| shared prefix: CTS, post-CTS repair, pin access, routing | ~13 min |
| each repair leaf | ~22 min |
| one arm, end to end | 35 min |

**The noise floor is exactly zero.** Two leaves with identical configuration,
forked off one routed prefix, returned bit-identical metrics -- WNS
`-0.1868625307379131` twice, same TNS, same instance count, same buffer count,
same area. Only wall-clock differed, by one second.

That is the load-bearing measurement. It means better/worse can be *decided*
rather than argued, without statistics. It also means that when a flow-level
A/B of a repair change produces "some designs better, some worse", the cause
is not run-to-run variance: repair runs at floorplan, place, CTS and global
route, so an early difference changes the placement and everything after it.
The ambiguity is confounding, and no amount of hardware fixes it. Forking one
stage off a shared prefix does.

## The idea

### A verdict vocabulary, with the nulls named

    not-applicable   a platform or library gate closed before the algorithm
                     was reachable at all
    inert            reachable, ran, committed nothing
    better           dominates on every declared axis
    worse            dominated on every declared axis
    trade            better on some axes, worse on others
    not-scored       the budget ran out; the count is UNKNOWN, not zero

The last two are the ones that matter. `trade` is the vocabulary the golden
files lack. `not-scored` exists because a killed leaf and a leaf that
committed nothing produce identical silence in the log, and reporting the
first as the second publishes a null as a result.

**No verdict is admissible unless the algorithm's own committed-move count is
non-zero and the phase is known to have completed.** Most arms measure
nothing; a scorer that does not check this reports noise as an effect.

### A front, not a default

`repair_timing -sequence` is already a configuration space and the moves are
already the algorithms under development, so a front over sequences is a name
for what the architecture implies rather than a new concept.

The value is that it changes the reviewable question from "is this better?",
which is usually unanswerable, to "does this add an undominated point, and
which region does it own?", which is decidable and cheap. A change that helps
wire-dominated designs and hurts others currently has to beat the default
everywhere or die; on a front it has somewhere to land.

Three constraints, or it rots:

* **Never average across designs.** The front is per design; the aggregate is
  a count of dominance. A mean over designs where the change is inert dilutes
  toward zero and reports as a small win -- which is exactly the shape of the
  unfalsifiable "average improvement on public CI benchmarks" claim that
  motivates this document.
* **A relevance gate.** A degenerate variant can be undominated at a corner
  no real design occupies. Without a gate the front becomes a museum.
* **A retirement rule.** Every point on the front is code someone maintains
  through every refactor. Dominated points get deleted.

A front does not choose the default. Somebody still has to say what runs when
the user says nothing, and that is a policy decision that should be made out
loud rather than fall out of a chart.

### The ledger is the durable artifact

Not the harness -- the accumulated record of **per-design yield**: which
designs produce verdicts, for which classes of change, and which have never
produced one. A design that scores `inert` for every change ever measured is
spending CI time and returning no information, and this says so with a number.
One that is the only design to catch some change is load-bearing and must
never be dropped.

That is a measured answer to "what should OpenROAD test", and it is the half
of this that gets more valuable with each pull request scored, rather than
being read once.

Its sharpest use is the **minimum sufficient design**: the cheapest design
that still yields a verdict for a given class of change. Under a fixed budget,
choosing the design *is* the score's central decision.

### Calibrate by back-testing merged pull requests

Merged QoR changes are free ground-truth labels: hundreds of changes
maintainers believed were improvements. Running them through the scorer gives
the suite a property it currently lacks -- a detection rate -- and turns "our
benchmark set is good" from an assertion into a measurement.

Two cautions:

* **Revert-from-master is not the counterfactual.** It measures removing a
  change from a tree that has grown around it. The true counterfactual is
  applying forward at the merge base. Use revert as a cheap screen and apply
  forward for what the screen flags.
* **"Merged" is a noisy label.** Many changes merge without anyone measuring
  anything, so an inert back-test cannot distinguish a blind suite from a
  change that did nothing. Only the committed-move count separates them.

The natural first cohort is the rsz move pull requests: self-contained
additions gated behind `repair_timing -sequence`, so the A/B is a string
rather than a build.

## The budget decides the shape

The score gets **30 minutes on one CI server**. Against the measured costs
above, three arms run sequentially on one design is 105 minutes, so the shape
follows from the budget rather than the other way round:

1. **Cache the pre-repair routed ODB.** The prefix is a pure function of
   (design, base binary) and is currently recomputed identically per arm --
   13 minutes burned three times to produce the same bytes. The seam that
   creates the fork point is where the cache cut belongs. A cache *miss* means
   no score, not a slow score.
2. **Run arms concurrently.** Separate processes, different binaries.
3. **Spend the budget on one design**, chosen by the ledger.

What 30 minutes buys:

| tier | cost | result |
|---|---|---|
| static gate | seconds | `not-applicable` verdicts, free |
| bit-identity check | one hash | full verdict for the "byte-identical, faster" class |
| one scored design | ~22 min | one region, one verdict |

**A durable test here does not mean a CI gate.** Flow runs cannot gate a pull
request. What can run per-commit is the free tier; the measured tier runs on
demand and its output is the ledger. Confusing the two turns an instrument
into an unmaintainable CI burden.

## The weakness: bespoke cost per pull request

The strongest objection, and it comes from the exercise that motivated this
document. Scoring 10662 needed work that no harness derived:

* **A seam in ORFS.** `patches/0050` cuts `global_route.tcl` between routing
  and incremental repair so one routed design can feed many repair
  configurations. Worth being precise about what it bought: without it the
  study still works, each leaf just re-runs pin access and routing for another
  13 minutes. **The seam bought budget compliance, not correctness.** It is
  also per *stage*, not per pull request -- every post-GR repair change reuses
  it -- so the cost is bounded at maybe five to ten seams for the whole flow.
* **Per-change semantics, which do not automate away.** Where the change acts,
  what turns it on, and what counts as "it fired". For 10662: a repair move,
  opt-in via `-sequence`, self-reporting through `Replaced N buffers with
  inverters`. All three came from reading the source.
* **Instrumentation asymmetry, the worst case.** The admission rule rests on
  the algorithm reporting its own actions. rsz happens to print that count; a
  change in `gpl` or `drt` may print nothing comparable, and then counting has
  to be *added*. Add it only to the arm and the comparison is corrupted; add
  it to both and neither binary is the one under review. There is no clean
  answer, only disclosure.

So the honest scope is narrower than the pitch: **cheap for the Nth pull
request in a class already paid for, expensive for the first of a new class.**
The rsz move cohort is cheap now because 10662 paid the entry fee; a `drt`
change starts from zero.

That should be falsifiable rather than argued. **Record the setup cost per
pull request in the ledger** beside the verdict -- seams written, gate
predicate lines, whether instrumentation was needed. If that cost does not
fall sharply by the second and third pull request in a class, the idea has
failed on its own terms and should be dropped rather than defended.

## What is deliberately not decided

* Where the ledger lives, and what the target is called.
* Whether reducing `-repair_tns` or capping `max_passes` to fit the budget
  preserves the verdict. It cuts leaf time directly and it can silently make
  an arm inert, so it is adoptable only after a full run and a reduced run are
  shown to agree on the same change.
* Whether a third-party score is something maintainers would act on. Untested,
  and the only way to find out is to produce one.

## What is happening instead, now

Scoring a single pull request end to end. If that does not produce something a
maintainer can hold an opinion about, none of the above is worth building.
