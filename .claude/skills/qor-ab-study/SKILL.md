---
name: qor-ab-study
description: Measure whether an OpenROAD PR moves the QoR Pareto front, as an A/B run over ORFS designs in bazel-orfs. Use when asked to test, benchmark, or gather data on an OpenROAD/ORFS pull request that claims a QoR improvement, or to decide whether a change is worth taking. Covers picking a baseline, proving the binary swap is real, choosing designs by measurement rather than intuition, and the silent-failure modes that make a study report clean numbers for an experiment that never ran.
---

## The one thing to internalise

In a QoR harness, **the default failure mode is quiet wrong data, not a
crash.** Every bug found while building this failed by producing
complete, well-formed, plausible metrics for an experiment that had not
happened. Absence of an error is not evidence the measurement occurred.

Budget your effort accordingly: assertions that the thing under test
actually ran are worth more than the analysis code.

## This needs a domain expert in the loop

An agent can do the mechanical rigor — verify the swap, close the
arithmetic, hold the conditions fixed. It cannot reliably tell whether
the experiment is *aimed* correctly. A study is only useful if it is:

* **powerful enough** — a design big enough, and with an actual problem
  to fix, for the change to have anything to act on;
* **economical** — cross products of designs × conditions explode; a
  smoke test on the right design beats a sweep over the wrong ones;
* **not confounding a null with a positive** — "no difference" from an
  invalid condition is not a result.

Get the PR's intent from someone who understands it before spending
compute. Ask what the change is supposed to bite on, and design the run
to give it that.

## Order of work

### 1. Baseline: rebase the PR onto current master

Measure against what ships today, not the PR's parent. Intervening work
can wash out or amplify the change. Cherry-pick the PR onto
`origin/master`, and state both SHAs in the write-up.

Then diff the two trees and confirm the only differences are the PR's —
and note which of them are binary-affecting (goldens and tests are not).

### 2. Prove the binary swap is real BEFORE any flow run

Build both arms, then run a cheap in-tree regression that the PR's own
goldens change, with each binary, and diff. If the outputs are identical,
stop: you are about to measure one binary twice.

`.claude/skills/byo-openroad` covers the BYO loop. Select the arm per
invocation with `OPENROAD_EXE=` as a make-style argument so no local path
is baked into a committed file — this repository is public.

### 3. Is the change even reachable by default?

Many OpenROAD options are opt-in. Check whether the code path is in the
default configuration at all; if it is not, a stock flow measures nothing
and you need a `config.mk` change (or an ORFS patch) to reach it.

Keep a `stock` arm anyway. Bit-identical results there is a real finding:
the PR cannot affect existing users.

### 4. Choose designs by measurement, not intuition

**This decided the outcome more than anything else.** Write a probe that
measures whether a design can exercise the change at all, run it over
candidates, and pick from the ranking. For a resizer move that trades
drive strength, the two properties were high-fanout nets and loads with a
smaller swappable sibling (`report_equiv_cells`); the first design tried
scored 17.5% and showed nothing, while another scored 29.3% and showed a
consistent effect.

Platform can matter more than design — asap7 offered 17–29% headroom,
sky130hd 2–7%.

### 5. Assert the baseline has a problem to fix

**A QoR arm is only valid if the baseline has negative slack.** A design
that closes has nothing to repair, so a repair-stage measurement on it is
vacuous — and it will report clean zero deltas that look exactly like a
null result.

ORFS designs are calibrated to sit a percent or two past closure, which
is what makes them good test cases. Anything that makes the design faster
— notably a faster library — destroys that calibration. ORFS's own
`aes_lvt` retimes its clock relative to `aes` for precisely this reason.
If you add a library variant, retune the period and *measure* where it
landed.

### 6. Put the fork point where the prefix is actually shared

`fork` earns its keep through the shared prefix (`docs/fork.md`), so
measure the prefix before reaching for it. Forking before the whole
cts+grt stage shared ~1% of a leaf; forking after routing, so leaves vary
only the repair, shared ~60%. Getting there needed an ORFS patch adding a
seam — carry it, do not work around it.

Only knobs that act *after* the fork point belong inside the fork.
Anything that must be set earlier (a clock period, a library) is an outer
dimension: a separate invocation with its own prefix.

## Silent-failure checklist

Each of these produced clean numbers and no error.

* **A failed stage that ORFS caught.** ORFS catches a failed
  `global_route`, writes artifacts and returns, so the repair phase is
  skipped and the leaf still writes a full metrics record. **Assert the
  phase completed**; propagate a status rather than ignoring it.
* **A constraint that did not take.** `[$clk period]` is STA-internal
  seconds; `create_clock -period` wants user units. Passing it through
  made a ~zero-period clock — slack −954, repair grinding for ten
  minutes, which reads as a slow design rather than a bug. **Read every
  derived constraint back and assert it.**
* **A library that loaded but did nothing.** `load_design` on a `.odb`
  calls `read_db`, not `read_lef`: the master set is frozen at floorplan
  time. Setting `ASAP7_USE_VT` at run time read 15 liberties and added
  zero masters, giving bit-identical results with no diagnostic. **Count
  masters, not liberty cells.**
* **A patched-in design with no targets.** `orfs_design()` returns early
  on a key missing from `DESIGNS`, so a design added by a patch parses
  and declares nothing. (Fixed by watching the designs tree; the shape
  recurs wherever a lookup miss is a silent skip.)
* **A parser that matched nothing.** `report_equiv_cells` prints a table,
  not bare names; taking whole lines as names reported **0% headroom on
  every design** — a plausible number from a parser matching nothing.
  **Sanity-check a metric that is uniform across inputs.**
* **`tee` traps, three separate times.** It evaluates its body as
  `{*}$body`, which splits a braced body into words *without*
  substituting them — build the command with `[list ...]`. It stores
  captured text in the variable named by `-variable` and *returns the
  wrapped command's result*. And `utl::tee` is ambiguous with the C++
  `teeFileBegin`/`teeStringBegin` helpers; call `tee` unqualified.
* **A walk that "succeeded" with dead leaves.** `fork` returns a status
  dict and a failed child does not stop the walk — by design. Bazel's
  exit code says the walk ran, not that leaves produced anything. **Check
  the statuses and fail on missing leaves.**

## Reporting

Per-leaf logs are mandatory: forked siblings share one stdout, so
interleaved output cannot be attributed. `tee -file` per leaf.

Prefer mechanism over effect size. "Removing the fanout gate surfaces
exactly 174 more drivers, `21130 + 174 = 21304`, and all 174 are rejected
downstream anyway" is worth more to a maintainer than a delta table.

State the flaws. One design, one run per point, no noise estimate,
stopping at global route — say so. A method demonstration with stated
limits is honest; the same run presented as a study is not.

Do not publish a plot of an invalid condition. Near-zero bars from a
design that closed look exactly like a null result.

## Related

* `docs/fork.md` — the fork/join idiom and when it pays
* `.claude/skills/byo-openroad` — building and injecting an arm's binary
* `.claude/skills/orfs-deps-preflight` — before committing to a long run
* `.claude/skills/repair-timing-grt` — repair_timing at global route
* `docs/studies/size-down-fanout-11320/` — a worked example, flaws and all
