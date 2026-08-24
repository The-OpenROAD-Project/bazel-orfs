# Estimation Ladder

**How close can you get to the clock period the flow would give you,
without running the flow?**

The baseline throughout is running floorplan through global route and
reading the timing off the result. Everything here is measured against
that, because that is the thing you would otherwise have to do.

- **multiplier (simple)**: the flow takes 41s. The estimator gets within **1.6%** of it in **6.35s** -- about **7x faster**.
- **multiplier_top (macro array)**: the flow takes 668s. The estimator gets within **3.7%** of it in **29.8s** -- about **22x faster**.

### Why the estimate is off at all

The estimator places cells but never routes them, so it works from
straight-line wire estimates. The router builds longer wires than that
-- detours, congestion, vias -- so every path comes out optimistic.
That is what pre-route means, and it is not a defect.

### The useful part: it is off by nearly the same amount everywhere

The estimator is not erratic, it is consistently optimistic. Almost
every path is short by close to the same amount, so **one correction
term removes most of the error**, and a term worked out on one design
still helps on another. Adding that correction to plain global
placement beats an uncorrected run that also pays for a clock tree and
global routing, at a fraction of the runtime. Much of what the
expensive stages appear to buy is an offset you can subtract for free.

The correction is worth more to the cheap rungs than the expensive
ones. On rungs that are already accurate, a correction borrowed from
another design makes them worse, because what is left of their error
belongs to that particular design.

### The limit: a good speedometer, a poor map

It predicts the period well and it is poor at telling you *which*
paths are critical. Of the ten genuinely worst paths, the estimator
puts only one to three of them in its own worst ten on the macro
design -- and picking at random would get one. Spending more runtime
does not fix it: on the simple design the 0.012s synthesis-only
estimate finds more of the worst paths than the 6.9s estimate that
predicts the period twenty times more precisely.

So for *what clock period will this close at*, the estimator works.
For *which path do I go fix*, it does not replace the flow.

### What did not help

- `-place_ios`, letting placement move the IO pins: fastest rung,
  worst accuracy.
- `-virtual_cts`, a cheap stand-in clock tree: worse than doing
  nothing about the clock at all.
- `repair_timing` at its default setting: 48s of runtime, no
  measurable change to the answer.
- Fancier corrections. A cubic, an isotonic fit, a Gaussian process --
  all fit the design they were tuned on better and all transfer to a
  new design worse. The Gaussian process reaches zero error on its own
  design, which is memorisation, and then does worse than no
  correction at all on the other one.

A real clock tree, by contrast, was worth it: it cut the error by a
third for under two seconds, because it captures the insertion delay
through the macros that an ideal clock hides.

### One thing to know before copying a configuration

Several of the fastest rungs skip the macro placer. Global placement
does then position the macros itself, and their locations are real --
but twelve of the hundred and twenty macro pairs end up overlapping,
where the macro placer leaves none. That is serviceable to estimate
timing from and impossible as a floorplan. These rungs are estimators,
not placements.

---

## Results per design

## multiplier (simple)

Running the flow itself -- floorplan through global route, the baseline this is all measured against -- takes **41s**. The cheapest rung on the front is 3442x faster than that at 21.3% error, and the most accurate is 6x faster at 1.1%.

Sampled 54 near-critical reg2reg paths. Recall@10 by chance is 0.19: a rung scoring at or below that has no skill at picking the critical paths.

Rung A explored 241 configurations.

7 front points across 0.012s to 6.91s. The widest gap (0.690) spans 0.012s to 0.96s and is structural rather than unexplored: it separates the configurations that skip placement from those that run it. Of 59 placed configurations timed here the fastest took 0.96s, so there is no cheap-but-placed estimate to be found in between -- the choice is binary.

| rungs                                       |   runtime_s |   mean_rel_err |   kendall_tau |      bias |   spread |   worst_recall |
|:--------------------------------------------|------------:|---------------:|--------------:|----------:|---------:|---------------:|
| synth only                                  |       0.012 |        0.2132  |        0.8532 | -0.2132   |  0.01367 |            0.8 |
| place, GRT(1)                               |       0.96  |        0.05292 |        0.8519 | -0.05292  |  0.02335 |            0.7 |
| place, NO macro place, place_ios, GRT(11)   |       1.05  |        0.0474  |        0.7834 | -0.04566  |  0.03353 |            0.7 |
| place, place_ios, vCTS, prop, rd, GRT(19)   |       2.849 |        0.04299 |        0.5709 | -0.02104  |  0.05345 |            0.5 |
| place, NO macro place, TD, vCTS, rd, GRT(1) |       3.541 |        0.02571 |        0.8644 | -0.02571  |  0.01402 |            0.8 |
| place, NO macro place, TD, RD, GRT(28), rt  |       6.348 |        0.01606 |        0.863  | -0.01411  |  0.01161 |            0.7 |
| place, TD, vCTS, CTS, rd, GRT(18), rt       |       6.906 |        0.01082 |        0.8798 | -0.008003 |  0.0101  |            0.6 |

![multiplier (simple) accuracy](pareto_multiplier.png)

![multiplier (simple) ranking](ranking_multiplier.png)

![multiplier (simple) bias](bias_multiplier.png)

## multiplier_top (macro array)

Running the flow itself -- floorplan through global route, the baseline this is all measured against -- takes **668s**. The cheapest rung on the front is 27840x faster than that at 27.3% error, and the most accurate is 10x faster at 3.4%.

Sampled 99 near-critical reg2reg paths. Recall@10 by chance is 0.10: a rung scoring at or below that has no skill at picking the critical paths.

Rung A explored 228 configurations.

6 front points across 0.024s to 65.9s. The widest gap (0.808) spans 0.024s to 14.4s and is structural rather than unexplored: it separates the configurations that skip placement from those that run it. Of 13 placed configurations timed here the fastest took 14.4s, so there is no cheap-but-placed estimate to be found in between -- the choice is binary.

| rungs                                     |   runtime_s |   mean_rel_err |   kendall_tau |      bias |   spread |   worst_recall |
|:------------------------------------------|------------:|---------------:|--------------:|----------:|---------:|---------------:|
| synth only                                |       0.024 |        0.2729  |        0.7073 | -0.2729   |  0.04208 |            0.1 |
| place, NO macro place, RD, CTS            |      14.42  |        0.1504  |        0.7675 |  0.1349   |  0.08277 |            0.3 |
| place, NO macro place, TD, RD, vCTS, prop |      21.15  |        0.05026 |        0.6562 | -0.04012  |  0.05995 |            0.2 |
| place, NO macro place, TD, RD, vCTS, CTS  |      29.28  |        0.04917 |        0.5143 | -0.007675 |  0.07096 |            0   |
| place, NO macro place, rd, GRT(1)         |      29.77  |        0.03718 |        0.7168 | -0.006053 |  0.06823 |            0.2 |
| place, place_ios, vCTS, CTS, rd           |      65.94  |        0.03433 |        0.7287 | -0.0105   |  0.05078 |            0.1 |

![multiplier_top (macro array) accuracy](pareto_multiplier_top.png)

![multiplier_top (macro array) ranking](ranking_multiplier_top.png)

![multiplier_top (macro array) bias](bias_multiplier_top.png)

## Does the bias transfer between designs?

The scale factor is fitted on `multiplier` and applied unchanged to
`multiplier_top`, which never contributed to it. **oracle** is what a
constant fitted on `multiplier_top`'s own ground truth would have
achieved -- the ceiling the transferred number is measured against,
not a result in itself.

| rung           |   scale |   raw err |   transferred |   oracle | helped   |
|:---------------|--------:|----------:|--------------:|---------:|:---------|
| place_only     |   1.121 |   0.09285 |       0.02899 |  0.02411 | yes      |
| place_ios      |   1.119 |   0.1611  |       0.06453 |  0.03256 | yes      |
| virtual_cts    |   1.158 |   0.112   |       0.03956 |  0.03125 | yes      |
| cts            |   1.105 |   0.06058 |       0.04609 |  0.02902 | yes      |
| cts_grt        |   1.053 |   0.03252 |       0.05957 |  0.03331 | no       |
| cts_grt_repair |   1.053 |   0.03252 |       0.05957 |  0.03331 | no       |

Rank correlation is absent from this table on purpose: it is
invariant under a positive scale factor, so calibration cannot
change the order the paths come out in, only how wrong the numbers
are.

---

## How we measured it

### The ground truth

The flow is run properly -- floorplan, placement, CTS, global route --
and the timing read off the result with propagated clocks and
global-routing parasitics. Up to 100 reg2reg paths are sampled from
the worst quarter of the period range, in ten buckets, so the sample
is spread across the near-critical paths rather than piled on the
single worst one. A *register* here can be a macro. The estimator has
to report every sampled path: one it cannot find is an error, not a
path to quietly drop, because dropping the awkward ones would make any
configuration look good.

The flow runtime it is compared against is the floorplan-through-
global-route stages summed from their own logs. Synthesis is excluded
from both sides, since both start from the same post-synthesis
netlist.

### Why runtime and accuracy are measured separately

Accuracy is a property of the placement and the parasitics, so many
estimators can run at once without affecting it. Runtime is not: eight
concurrent runs measure contention between siblings as much as the
settings under test. So there are two passes. The first sweeps the
knob space concurrently and records accuracy only. The second re-runs
selected configurations one at a time and times them, with whatever
thread count ORFS hands the tool, three times over, taking the median
and adding repeats when they disagree by more than 5%.

The second pass chooses what to measure adaptively. Because the first
pass already knows every configuration's accuracy, the only open
question is whether a configuration is fast enough to matter, so it
measures wherever a runtime model thinks a configuration might beat
the best already timed at that accuracy.

### The accuracy numbers

- **mean relative error** -- the average of |estimate - truth| / truth
  over the sampled paths.
- **bias** and **spread** -- the average signed error, and the
  variation around it. Reported separately because they mean different
  things: an estimator that is wrong by a consistent amount can be
  corrected with one number, and one that is wrong erratically cannot,
  even when their mean relative errors match.
- **Kendall tau** -- rank correlation between estimated and true path
  order. 1 is perfect agreement, 0 is unrelated.
- **recall@10** -- of the ten truly worst paths, how many the
  estimator also puts in its worst ten. Chance level is ten divided
  by the number of sampled paths (multiplier: 0.19, multiplier_top: 0.10); a rung at or below that
  has no skill at all rather than a little.

### The correction

Ten families were fitted -- a multiplicative constant, an additive
offset, an affine fit, a power law, quadratic and cubic polynomials,
an isotonic fit, a Gaussian process, and Bayesian linear regression --
and each was scored three ways: on the design it was fitted to, on
held-out paths of that design, and on the *other* design entirely.
Only the third number says anything, because a correction fitted
against the ground truth it is then graded on is measuring its own
free parameter.

Every one of these reads only the estimate, and a function of the
estimate alone cannot reorder the paths. So none of them can improve
rank correlation or worst-path recall -- the ordering after correction
is identical, which is checked rather than assumed. Fixing the order
would need a per-path correction using features of each path, which is
a different study.

### What the numbers do not cover

Two small designs, one of which is 400um square. The knob-to-outcome
associations come from a sweep that concentrates its sampling near the
best configurations, so they are suggestive rather than controlled
experiments. The macro design's front rests on 14 timed
configurations, and the simple design's search hit its budget before
meeting its own spread criterion.

### Reproducing it

```sh
bazel build //test/estimation_ladder:extract_ground_truth \
            //test/estimation_ladder:extract_ground_truth_top
bazel run //test/estimation_ladder:optuna_study        # accuracy sweep
bazel run //test/estimation_ladder:optuna_study_top
bazel run //test/estimation_ladder:measure_runtime     # timed pass
bazel run //test/estimation_ladder:measure_runtime_top
bazel run //test/estimation_ladder:calibration_transfer
bazel run //test/estimation_ladder:calibration_models
bazel run //test/estimation_ladder:update-readme
```

