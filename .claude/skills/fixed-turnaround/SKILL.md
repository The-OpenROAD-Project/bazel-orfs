---
name: fixed-turnaround
description: >-
  Fix the turnaround time of an edit-run loop before the first run: name what the loop must
  test, measure each step of the vehicle, and shrink the vehicle and the loop until one
  iteration fits the budget (minutes); a bad choice then costs one short iteration instead of
  another long rebuild. Covers keeping the expensive upstream frozen (a C++ change is tested in
  its unit test, a script in a dirty lane on cached inputs, a binary change batched), and
  stopping a run whose iteration turned out longer than the budget, and knowing how long each
  step should take so a suspiciously long one is debugged, stopped, fixed and restarted rather
  than waited on. Use before building a test vehicle, before iterating on a flow script or a
  carried patch, whenever a fix waits on a rebuild of things the fix does not touch, and when
  a step runs longer than it should.
---

> **Repo**: Applies to every edit-run loop in bazel-orfs and the workspaces that depend on it: a toy design, a flow script, a carried OpenROAD patch.

A loop that takes half an hour per iteration does not run four bugs in two hours; it runs them in four half hours, and each one was visible in the first seconds of the run that found it. Fix the turnaround first and the bugs come cheap. Running the long loop and waiting is the bad choice, every time it is repeated.

ARGUMENTS: $ARGUMENTS

## The rule

1. **Name what the loop tests.** One sentence: the mechanism, not the design. "The dissolve top level: strip, rows, CTS, global route and the crossing check," not "the toy."
2. **Set the budget before the first run.** Minutes per iteration of the whole loop. Write it down next to the plan.
3. **Measure the vehicle, step by step.** Stage times from the logs (`Took N seconds`, the elapsed tables, a perf index), not from a guess. The step that takes the most is where the vehicle is wrong.
4. **Shrink until it fits.** The smallest design that still exercises the mechanism: a die sized to its cells (a stage's time follows die area, not cell count), the stages the mechanism does not touch skipped or reused, repairs off unless they are under test.
5. **Keep the expensive upstream frozen.** An iteration rebuilds only what the edit touches:
   - a C++ change in a carried patch is tested in its unit test (seconds), and the patch is batched into the flow once it passes, because every patch to the tool re-keys every stage of every flow;
   - a flow script is iterated in a dirty lane on the cached outputs it reads (`dirty-lane`), and goes back into the build when it works;
   - a bring-your-own binary (`byo-openroad`) tests a tool change in a lane before it becomes a patch.
6. **Stop a run that blows the budget.** Do not wait for it: stop it, find the step that took the time, fix the vehicle, then run again.
7. **Know how long each step should take, and do not wait forever for one that should have been fast.** Before launching, write down what each step ought to cost from what it does (a synthesis of a few thousand cells is seconds, a partition of a core minutes). When a step runs suspiciously long, start debugging it while it runs: what is it doing (`perf`, the log's last lines, the process's inputs), and is that what it should be doing. Occasionally there is nothing for it and the step is that long; mostly, unexpectedly long means something upstream is wrong, and stop, fix and restart beats waiting.

## What it looks like

- A Tcl script for a top level that dissolves cached macros is run in a lane on their global-route `.odb` files: an error in the script costs the seconds it took to reach it, not a rebuild of every macro.
- An OpenROAD patch's new option is driven from its gtest until it passes; one patch, one rebuild of the flows.

## Anti-patterns

Each of these came from one afternoon building the parent as a macro, on a toy and on XiangShan's tile:

- A toy spread over 4.6 mm² to test a clock-distance question that had since been dropped: 30 min per iteration, nearly all of it power grid, placement and routing of empty die.
- Five script and binding bugs (a macro larger than the core, a SWIG method name, a dont_touch order, an odb placement-status name, a Tcl variable scope), each found seconds into a 30 min rebuild, each fix waiting another 30 min, because every fix to the carried OpenROAD patch re-keyed all of the toy's macros.
- The tile's parent synthesis left running for hours in one step of ABC (`dch`, one network for the whole parent), when the tile's own flow synthesizes it in parallel partitions, one per kept module: the hierarchy had been flattened by mistake, and a look at what ABC was doing after the first half hour would have said so.

## Where the mechanics live

`dirty-lane` for the lane, `byo-openroad` for the binary loop, `no-paint-drying` for settling questions small before a long run, `orfs-deps-preflight` for checking that the loop runs the code path under test, `dogfooding` for watching a long run that grinds past its expected time.
