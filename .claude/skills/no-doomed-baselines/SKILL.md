---
name: no-doomed-baselines
description: >-
  Never wait for a doomed or pointless baseline. A baseline is the thing being replaced,
  measured; when it is known to grind (a pass whose time grows with the square or cube of the
  size, a stage stuck far past its expected time), running it to the end tells nothing the
  small sizes did not, and holds the machine and the Bazel server while it does. Probe the
  scaling at three small sizes, extrapolate, cap every point with a timeout, record a capped
  point as "over T, stopped" with the cause, and spend the machine on the thing being built.
  Use before starting a sweep or an A/B with a baseline arm, when a baseline point runs past
  its prediction, and whenever the machine is idle or blocked behind one action.
---

# Never wait for doomed and pointless baselines

> **Repo**: any bazel-orfs workspace. The rule is about measurement, not one tool.

A baseline exists to answer a question: is the new thing faster, smaller,
better? When the answer is already in hand from small sizes, the large
sizes of the baseline are paint drying. When the baseline grinds because
of a known pathology, its large sizes measure the pathology, not the
baseline. Either way, waiting for it is the slow turnaround the work set
out to remove, and a turnaround that cannot be made fast is itself a
negative result, to be written down rather than waited on.

## The rule

1. **Name the question before the sweep.** "Is yosys slower than the
   generator on this structure" is answered by where the curves cross,
   not by the last point.
2. **Probe the scaling small first.** Three sizes, seconds each. Times of
   1 s, 7.5 s and 74 s at depth 64, 128 and 256 predict the 512 point;
   there is no need to run it.
3. **Cap every point.** A timeout per point, a few times the prediction.
   A capped point is a result: "over 300 s, stopped, `opt_mem_priority`".
4. **Find the cause of a grinding point while it runs, small.** Reproduce
   it at a small size outside the flow, read the tool's own time summary
   (yosys's `Time spent:` line), and name the pass. Then decide: is the
   pathology the finding, or in the way of the finding?
5. **Stop it.** Kill the doomed actions and shut the Bazel server down if
   they hold it; a build blocked behind one doomed action blocks every
   other build in the workspace too.
6. **Never leave the machine idle or blocked.** Work that does not depend
   on the baseline goes ahead in the meantime.
7. **Fix the pathology only when it is in the way.** When the baseline's
   slowness is the thing the new work removes, it is the result; a fix
   for it is a separate concern, with its own measurement.

## Seen

In the yosys arm of a depth x width toy scan of array structures, the
512-deep counter and flag toys sat in canonicalization for more than 12
minutes, and the 512-deep age matrix for 19, while the
rest of the scan was done. Small probes had already named the causes:
`opt_mem_priority` solving every pair of a memory's write ports with SAT
(1 s, 7.5 s, 74 s at 64, 128, 256 entries), and `opt_clean` on a memory
whose every word is read at a constant address (0.3 s, 5 s, 77 s). The
512-deep points added nothing but wall time; they were stopped, and the
question moved to the generator's path, where every toy took under 2 s.
