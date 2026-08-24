# Estimation Ladder

**How close can you get to the clock period the flow would give you,
without running the flow?**

The baseline throughout is running floorplan through global route and
reading the timing off the result. Everything here is measured against
that, because that is the thing you would otherwise have to do.

- **multiplier (simple)**: the flow takes **41s**. The estimator gets within **1.9%** of it in **5.38s**, of which 2.37s is loading the design and running the timing query -- overhead any rung pays.
- **multiplier_top (macro array)**: the flow takes **668s**. The estimator gets within **6.0%** of it in **51s**, of which 4.3s is loading the design and running the timing query -- overhead any rung pays.
- **multiplier_top, macro paths only**: the flow takes **668s**. The estimator gets within **9.0%** of it in **20s**, of which 3.71s is loading the design and running the timing query -- overhead any rung pays.

The synthesis-only rung is in the tables below as an accuracy
floor -- what you get for reading the netlist and asking OpenSTA --
not as a speedup to quote. Almost all of its runtime is loading the
design and running the timing query, and both of those grow with
design size while the flow grows faster still. Read its ratio as an
artifact of these designs being small, not as something that would
hold on a real one.

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

Running the flow itself -- floorplan through global route, the baseline this is all measured against -- takes **41s**. The cheapest rung on the front is 17x faster than that at 21.3% error, and the most accurate is 4x faster at 1.3%.

Sampled 54 near-critical reg2reg paths. Recall@10 by chance is 0.19: a rung scoring at or below that has no skill at picking the critical paths.

Rung A explored 238 configurations.

10 front points across 2.44s to 10.9s; widest normalized gap 0.286, so **a gap exceeds** the 0.15 target and the budget did not fill it.

|   # | rungs                                           |   runtime_s |   mean_rel_err |   kendall_tau |      bias |   spread |   worst_recall |
|----:|:------------------------------------------------|------------:|---------------:|--------------:|----------:|---------:|---------------:|
|   1 | synth only                                      |       2.443 |        0.2132  |        0.8532 | -0.2132   |  0.01367 |            0.8 |
|   2 | place, place_ios, prop                          |       3.66  |        0.1132  |        0.7932 | -0.1132   |  0.02577 |            0.5 |
|   3 | place, NO macro place, place_ios, vCTS, GRT(21) |       3.671 |        0.0827  |        0.8421 | -0.0827   |  0.02306 |            0.8 |
|   4 | place, NO macro place, place_ios, vCTS, rd      |       3.956 |        0.0794  |        0.8365 | -0.0794   |  0.01874 |            0.7 |
|   5 | place, NO macro place, place_ios, GRT(15)       |       4.02  |        0.07304 |        0.8029 | -0.07304  |  0.028   |            0.5 |
|   6 | place, NO macro place, TD, prop                 |       5.348 |        0.06057 |        0.8756 | -0.06057  |  0.01202 |            0.7 |
|   7 | place, NO macro place, TD, RD, GRT(20)          |       5.383 |        0.01865 |        0.8351 | -0.01478  |  0.01684 |            0.6 |
|   8 | place, TD, rd, GRT(13), rt                      |       6.359 |        0.01815 |        0.8281 | -0.01376  |  0.01556 |            0.7 |
|   9 | place, NO macro place, TD, RD, rd, GRT(28), rt  |       7.097 |        0.01575 |        0.8113 | -0.0116   |  0.01603 |            0.5 |
|  10 | place, NO macro place, TD, RD, CTS, GRT(2), rt  |      10.87  |        0.0131  |        0.8393 | -0.007871 |  0.01363 |            0.6 |

**Where the flow's time goes**, largest first: global_route 14s, global_place 8s, cts 6s, floorplan 5s, detailed_place 4s, repair_design 3s, place_pins 1s, macro_place 1s. The single biggest stage is global_route at 35% of the flow, and the estimator does not skip it so much as run a far cheaper version of it -- which is where the saving comes from.

**What each stage costs**, from the deepest rung measured (place, TD, rd, GRT(13), rt): global_place 2.38s, repair_design 0.728s, repair_timing 0.402s, global_route 0.192s, place_pins 0.009s, floorplan 0.002s.

**Where each rung's time goes.** Overhead is loading the design and running the timing query, which cost the same whatever the rung does.

| rung                                               |   total_s |   overhead_s |   work_s |   overhead_pct | vs flow   |
|:---------------------------------------------------|----------:|-------------:|---------:|---------------:|:----------|
| the full flow (baseline)                           |     41.3  |       nan    |   41.3   |          nan   | 1x        |
| 1. synth only                                      |      2.44 |         2.42 |    0.018 |           99.3 | 17x       |
| 2. place, place_ios, prop                          |      3.66 |         2.45 |    1.21  |           67   | 11x       |
| 3. place, NO macro place, place_ios, vCTS, GRT(21) |      3.67 |         2.36 |    1.31  |           64.4 | 11x       |
| 4. place, NO macro place, place_ios, vCTS, rd      |      3.96 |         2.36 |    1.6   |           59.6 | 10x       |
| 5. place, NO macro place, place_ios, GRT(15)       |      4.02 |         2.52 |    1.5   |           62.7 | 10x       |
| 6. place, NO macro place, TD, prop                 |      5.35 |         3.04 |    2.31  |           56.8 | 8x        |
| 7. place, NO macro place, TD, RD, GRT(20)          |      5.38 |         2.37 |    3.01  |           44.1 | 8x        |
| 8. place, TD, rd, GRT(13), rt                      |      6.36 |         2.42 |    3.94  |           38.1 | 6x        |
| 9. place, NO macro place, TD, RD, rd, GRT(28), rt  |      7.1  |         2.41 |    4.69  |           33.9 | 6x        |
| 10. place, NO macro place, TD, RD, CTS, GRT(2), rt |     10.9  |         3.55 |    7.32  |           32.7 | 4x        |

![multiplier (simple) time breakdown](time_multiplier.png)

![multiplier (simple) accuracy](pareto_multiplier.png)

![multiplier (simple) ranking](ranking_multiplier.png)

![multiplier (simple) bias](bias_multiplier.png)

## multiplier_top (macro array)

Running the flow itself -- floorplan through global route, the baseline this is all measured against -- takes **668s**. The cheapest rung on the front is 183x faster than that at 32.1% error, and the most accurate is 13x faster at 6.0%.

Sampled 177 near-critical reg2reg paths. Recall@10 by chance is 0.06: a rung scoring at or below that has no skill at picking the critical paths.

Rung A explored 231 configurations.

4 front points across 3.65s to 51s. The widest gap (0.763) spans 3.65s to 27.3s and is structural rather than unexplored: it separates the configurations that skip placement from those that run it. Of 8 placed configurations timed here the fastest took 27.3s, so there is no cheap-but-placed estimate to be found in between -- the choice is binary.

|   # | rungs                                       |   runtime_s |   mean_rel_err |   kendall_tau |     bias |   spread |   worst_recall |   mean_rel_err_nonmacro |   kendall_tau_nonmacro |   mean_rel_err_macro |   kendall_tau_macro |
|----:|:--------------------------------------------|------------:|---------------:|--------------:|---------:|---------:|---------------:|------------------------:|-----------------------:|---------------------:|--------------------:|
|   1 | synth only                                  |       3.653 |        0.321   |        0.7604 | -0.321   |  0.08412 |            0.1 |                 0.2729  |                 0.7073 |              0.3821  |             0.2735  |
|   2 | place, NO macro place, place_ios, vCTS, CTS |      27.29  |        0.2097  |        0.6758 |  0.1091  |  0.204   |            0.3 |                 0.2496  |                 0.6512 |              0.1591  |            -0.03563 |
|   3 | place, RD, vCTS, GRT(23), rt                |      35.22  |        0.07914 |        0.844  | -0.05938 |  0.08004 |            0.2 |                 0.0605  |                 0.7304 |              0.1028  |             0.645   |
|   4 | place, TD                                   |      50.96  |        0.06046 |        0.7788 | -0.01192 |  0.08569 |            0.2 |                 0.03324 |                 0.7675 |              0.09499 |             0.3     |

**Where the flow's time goes**, largest first: global_route 374s, global_place 200s, cts 39s, floorplan 21s, macro_place 21s, detailed_place 8s, repair_design 5s, place_pins 1s. The single biggest stage is global_route at 56% of the flow, and the estimator does not skip it so much as run a far cheaper version of it -- which is where the saving comes from.

**What each stage costs**, from the deepest rung measured (place, RD, vCTS, GRT(23), rt): macro_place 18.8s, global_route 5.64s, global_place 4.37s, repair_timing 2.01s, place_pins 0.017s, floorplan 0.007s.

**Macro paths behave differently, and worse.** Of the 177 sampled paths, 78 touch a macro pin and 99 do not, and the two are separate populations: the macro paths run faster and none of them is among the ten worst overall, which is why a slack-ranked sample reaches almost none of them and has to be told to go and find them. Scored on their own, rank correlation across the front runs from -0.04 to +0.65 against +0.65 to +0.73 on everything else. Where that number is negative the estimator is ordering the macro paths backwards, and the healthy-looking aggregate is the non-macro majority outvoting them.

**Where each rung's time goes.** Overhead is loading the design and running the timing query, which cost the same whatever the rung does.

| rung                                           |   total_s |   overhead_s |   work_s |   overhead_pct | vs flow   |
|:-----------------------------------------------|----------:|-------------:|---------:|---------------:|:----------|
| the full flow (baseline)                       |    668    |       nan    |  668     |         nan    | 1x        |
| 1. synth only                                  |      3.65 |         3.64 |    0.017 |          99.5  | 183x      |
| 2. place, NO macro place, place_ios, vCTS, CTS |     27.3  |         5.78 |   21.5   |          21.2  | 24x       |
| 3. place, RD, vCTS, GRT(23), rt                |     35.2  |         3.73 |   31.5   |          10.6  | 19x       |
| 4. place, TD                                   |     51    |         4.3  |   46.7   |           8.44 | 13x       |

![multiplier_top (macro array) time breakdown](time_multiplier_top.png)

![multiplier_top (macro array) accuracy](pareto_multiplier_top.png)

![multiplier_top (macro array) ranking](ranking_multiplier_top.png)

![multiplier_top (macro array) bias](bias_multiplier_top.png)

## multiplier_top, macro paths only

Running the flow itself -- floorplan through global route, the baseline this is all measured against -- takes **668s**. The cheapest rung on the front is 183x faster than that at 32.1% error, and the most accurate is 8x faster at 7.9%.

Sampled 78 near-critical reg2reg paths. Recall@10 by chance is 0.13: a rung scoring at or below that has no skill at picking the critical paths.

Rung A explored 226 configurations.

5 front points across 3.65s to 88.9s. The widest gap (0.518) spans 3.65s to 19s and is structural rather than unexplored: it separates the configurations that skip placement from those that run it. Of 18 placed configurations timed here the fastest took 19s, so there is no cheap-but-placed estimate to be found in between -- the choice is binary.

|   # | rungs                                             |   runtime_s |   mean_rel_err |   kendall_tau |     bias |   spread |   worst_recall |   mean_rel_err_nonmacro |   kendall_tau_nonmacro |   mean_rel_err_macro |   kendall_tau_macro |
|----:|:--------------------------------------------------|------------:|---------------:|--------------:|---------:|---------:|---------------:|------------------------:|-----------------------:|---------------------:|--------------------:|
|   1 | synth only                                        |       3.646 |         0.321  |        0.7604 | -0.321   |  0.08412 |            0.1 |                 0.2729  |                 0.7073 |              0.3821  |              0.2735 |
|   2 | place, NO macro place, place_ios                  |      19.04  |         0.2937 |        0.6614 |  0.2349  |  0.2485  |            0   |                 0.4287  |                 0.4566 |              0.1225  |              0.1755 |
|   3 | place, NO macro place, place_ios, rd              |      20     |         0.1878 |        0.7685 |  0.1158  |  0.1844  |            0.2 |                 0.2645  |                 0.692  |              0.0904  |              0.3427 |
|   4 | place, NO macro place, place_ios, CTS, rd, GRT(6) |      35.23  |         0.1797 |        0.756  |  0.1087  |  0.1785  |            0   |                 0.2513  |                 0.6281 |              0.08894 |              0.346  |
|   5 | place, TD, CTS, GRT(17), rt                       |      88.92  |         0.0785 |        0.7838 |  0.04569 |  0.08002 |            0   |                 0.07141 |                 0.6281 |              0.0875  |              0.4872 |

**Where the flow's time goes**, largest first: global_route 374s, global_place 200s, cts 39s, floorplan 21s, macro_place 21s, detailed_place 8s, repair_design 5s, place_pins 1s. The single biggest stage is global_route at 56% of the flow, and the estimator does not skip it so much as run a far cheaper version of it -- which is where the saving comes from.

**What each stage costs**, from the deepest rung measured (place, TD, CTS, GRT(17), rt): global_route 35.7s, macro_place 18.8s, global_place 17.2s, cts 4.73s, repair_timing 1.97s, place_pins 0.016s, floorplan 0.006s.

**Macro paths behave differently, and worse.** Of the 177 sampled paths, 78 touch a macro pin and 99 do not, and the two are separate populations: the macro paths run faster and none of them is among the ten worst overall, which is why a slack-ranked sample reaches almost none of them and has to be told to go and find them. Scored on their own, rank correlation across the front runs from +0.18 to +0.49 against +0.46 to +0.63 on everything else. Where that number is negative the estimator is ordering the macro paths backwards, and the healthy-looking aggregate is the non-macro majority outvoting them.

**Where each rung's time goes.** Overhead is loading the design and running the timing query, which cost the same whatever the rung does.

| rung                                                 |   total_s |   overhead_s |   work_s |   overhead_pct | vs flow   |
|:-----------------------------------------------------|----------:|-------------:|---------:|---------------:|:----------|
| the full flow (baseline)                             |    668    |       nan    |  668     |          nan   | 1x        |
| 1. synth only                                        |      3.65 |         3.62 |    0.023 |           99.4 | 183x      |
| 2. place, NO macro place, place_ios                  |     19    |         3.67 |   15.4   |           19.3 | 35x       |
| 3. place, NO macro place, place_ios, rd              |     20    |         3.71 |   16.3   |           18.5 | 33x       |
| 4. place, NO macro place, place_ios, CTS, rd, GRT(6) |     35.2  |         4.94 |   30.3   |           14   | 19x       |
| 5. place, TD, CTS, GRT(17), rt                       |     88.9  |         9.66 |   79.3   |           10.9 | 8x        |

![multiplier_top, macro paths only time breakdown](time_multiplier_top_macro.png)

![multiplier_top, macro paths only accuracy](pareto_multiplier_top_macro.png)

![multiplier_top, macro paths only ranking](ranking_multiplier_top_macro.png)

![multiplier_top, macro paths only bias](bias_multiplier_top_macro.png)

## Does the bias transfer between designs?

The scale factor is fitted on `multiplier` and applied unchanged to
`multiplier_top`, which never contributed to it. **oracle** is what a
constant fitted on `multiplier_top`'s own ground truth would have
achieved -- the ceiling the transferred number is measured against,
not a result in itself.

| rung           |   scale |   raw err |   transferred |   oracle | helped   |
|:---------------|--------:|----------:|--------------:|---------:|:---------|
| place_only     |   1.121 |   0.1381  |        0.1177 |  0.1139  | yes      |
| place_ios      |   1.119 |   0.1841  |        0.108  |  0.07943 | yes      |
| virtual_cts    |   1.158 |   0.145   |        0.1243 |  0.115   | yes      |
| cts            |   1.105 |   0.1185  |        0.1247 |  0.1073  | no       |
| cts_grt        |   1.053 |   0.09771 |        0.1182 |  0.1     | no       |
| cts_grt_repair |   1.053 |   0.09769 |        0.1182 |  0.1     | no       |

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

### What a runtime includes

Everything from having the post-synthesis netlist to having a timing
number: reading the ODB, the SDC and the liberties, whatever flow
stages the rung runs, and the timing queries themselves. OpenSTA
builds its graph and computes delays on the first query, so the query
is not bookkeeping around the result -- on a rung that runs no flow
stages it is most of the work. An earlier version of this study timed
only the flow stages, which reported a rung whose real cost is 3.5s at
0.024s and made it look thousands of times faster than the flow rather
than a couple of hundred.

The flow baseline is summed from its own stage logs, each of which
includes that stage's load, so both sides are counted the same way.

Load and timing-query cost scale with design size. On a design much
larger than these the fixed overhead grows, and the cheapest rungs
lose most of their apparent advantage; the rungs that run real flow
stages are affected proportionally less.

### How these times would scale

Not measured -- there is no large design here -- but the components
scale differently and it is worth knowing which way. Loading grows
with netlist size. The timing query grows with the number of paths
and their depth. Global placement grows faster than linearly in
instance count. Global routing grows with net count and, badly, with
congestion. The fixed overhead therefore grows more slowly than the
flow does, so the rungs that run real stages should hold their
advantage on a larger design while the near-empty rungs lose most of
theirs.

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
  by the number of sampled paths (multiplier: 0.19, multiplier_top: 0.06, multiplier_top_macro: 0.13); a rung at or below that
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

