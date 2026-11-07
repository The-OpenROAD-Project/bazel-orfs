---
name: openroad-field-guide
description: What is known about how OpenROAD, OpenSTA, yosys and ORFS behave when they hurt — per tool (synthesis, floorplan/PDN/pins, mpl, gpl, dpl, cts, rsz/repair_timing, grt, drt, OpenSTA, odb/parasitics) the log lines that say which phase is running and whether it converges or grinds, where the time and the memory go, the levers that work, what is futile or has no lever, and the history of what was tried here, what worked and which hills were died on, with the carried patches and upstream pull requests behind each. A body of knowledge that grows as problems are worked. Use first when a stage is slow, runs out of memory, grinds, or gives a bad period, before reading OpenROAD source or starting a measurement, and update it when a problem is understood.
---

# OpenROAD field guide

A stage is slow, runs out of memory, or the period will not come down.
This guide says where to look first and what to expect, so a diagnosis
starts from what was already learned instead of from the source.

It holds only what bites: a tool that works and is never a problem gets
no entry. One file per tool:

| File | Covers |
|---|---|
| [synth.md](synth.md) | yosys, slang, ABC, ORFS synth scripts |
| [floorplan.md](floorplan.md) | ifp, pdn, global connect, ppl |
| [mpl.md](mpl.md) | Hier-RTLMP macro placement |
| [gpl.md](gpl.md) | global placement, timing- and routability-driven modes |
| [dpl.md](dpl.md) | legalisation, pixel grid, DPO |
| [cts.md](cts.md) | TritonCTS, the latency balancer, the cts stage |
| [rsz.md](rsz.md) | repair_design, repair_timing, repair_hold |
| [grt.md](grt.md) | FastRoute, incremental grt, grt memory |
| [drt.md](drt.md) | TritonRoute, pin access, antenna repair |
| [sta.md](sta.md) | OpenSTA: threads, memory, silent wrong answers |
| [odb.md](odb.md) | odb, estimate_parasitics, rcx |

## Triage: where the time and memory usually go

| Stage | Usually slow because | Usually big because |
|---|---|---|
| synth | yosys frontend, per-kept-module canonicalisation, `extract_fa` | |
| floorplan | zero-wire `repair_timing` | hierarchical `link_design` |
| place | timing-driven `repair_design` x2, routability reverts, a second skip-io gpl | STA + parasitics inside gpl |
| cts | `repair_timing` setup + hold; the latency balancer timing everything | balancer arrivals, CRPR |
| grt | `repair_timing` with incremental grt, 4-5 full `estimate_parasitics`, serial maze loop | router graph + STA + parasitics + dpl pixel grid, all at once |
| route | the slowest worker per batch; post-route antenna loop re-running drt | drt's copy of the geometry |
| any | OpenSTA updates, `report_metrics`, odb read/write | |

**A repair loop is mostly the timer, not the moves** (bazel-orfs #978):
when a stage with repair in it is slow, look at STA and parasitics first.

**Before blaming a tool for a QoR change, perturb master**: net order is
noise. Creating empty dummy nets swings ibex TNS from -6 to -3,633 ps
(ORFS #4785); run many cheap designs, not a curated few (bazel-orfs
#981); runtime deltas under 10 % are noise.

## How to use it

1. Find the stage and the phase from the log: each file's "Reading the
   log" names the message IDs and what convergence looks like.
2. Read the file's "where the time/memory goes" and "futile" before
   trying a lever: a lever that is already known not to work costs a
   run.
3. Check "History" for whether the problem was already met, what was
   tried, and which carried patch or upstream pull request holds the fix.
4. Then measure, with the skills that own the mechanics:
   `openroad-debug`, `dirty-lane`, `odb-debug`, `repair-headroom`,
   `repair-timing-grt`, `cache-miss`, `scale-to-memory`.

## Growing it

Every problem worked to an understanding adds to it, in the same change
that fixes or records the problem, or as a pull request of its own with
one concern.

- **Add**: a log signature that tells phases apart, a measured time or
  memory split, a lever and what it bought, a lever that did nothing, a
  dead end with why. Numbers with their design and a reference (a
  bazel-orfs or upstream pull request, a carried patch, an
  `ideas/` entry). Mark what was read from code and not measured.
- **Delete**: an entry a bump made untrue (a carried patch retired, a bug
  fixed upstream) shrinks to one line in History or goes. Present tense
  describes the current pin.
- **Leave out**: how a tool works when it works; mechanics another skill
  owns (link to it); anything private: designs, machines, people's
  contact details, unpublished numbers.
- Keep each file to what helps diagnose: if an entry would not change
  what someone does next, it does not belong.
