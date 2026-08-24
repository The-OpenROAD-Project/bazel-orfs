# Estimation Ladder

How accurately can early flow stages estimate the minimum clock period
of the near-critical reg2reg paths, compared to a global-routed ground
truth -- and at what runtime cost?

Synthesis-only timing is optimistic: it sees no wires, and on a design
with macros it does not see the clock tree either, so macro clock
insertion latency lands straight in the estimated period. Adding early
placement, a clock tree, resizing and global routing buys that back at
increasing runtime -- the estimation ladder.

Runtimes come from a separate measurement pass that runs one estimator
at a time, so they are not contaminated by contention between
concurrent trials; accuracy comes from a much wider concurrent sweep,
which contention does not affect. Runtime is plotted on a log axis
because the ladder spans several orders of magnitude.

![Pareto Plot](https://github.com/The-OpenROAD-Project/bazel-orfs/blob/estimation-ladder-study/test/estimation_ladder/pareto_plot.png?raw=true)

![Bias and spread](https://github.com/The-OpenROAD-Project/bazel-orfs/blob/estimation-ladder-study/test/estimation_ladder/bias_spread.png?raw=true)

## multiplier (simple)

Ground truth flow runtime: 41 s.

Rung A explored 241 configurations.

7 front points across 0.012s to 6.91s. The widest gap (0.690) spans 0.012s to 0.96s and is structural rather than unexplored: it separates the configurations that skip placement from those that run it. Of 59 placed configurations timed here the fastest took 0.96s, so there is no cheap-but-placed estimate to be found in between -- the choice is binary.

| rungs                                     |   runtime_s |   mean_rel_err |   kendall_tau |      bias |   spread |   worst_recall |
|:------------------------------------------|------------:|---------------:|--------------:|----------:|---------:|---------------:|
| synth only                                |       0.012 |        0.2132  |        0.8532 | -0.2132   |  0.01367 |            0.8 |
| place, GRT(1)                             |       0.96  |        0.05292 |        0.8519 | -0.05292  |  0.02335 |            0.7 |
| place, place_ios, GRT(11)                 |       1.05  |        0.0474  |        0.7834 | -0.04566  |  0.03353 |            0.7 |
| place, place_ios, vCTS, prop, rd, GRT(19) |       2.849 |        0.04299 |        0.5709 | -0.02104  |  0.05345 |            0.5 |
| place, TD, vCTS, rd, GRT(1)               |       3.541 |        0.02571 |        0.8644 | -0.02571  |  0.01402 |            0.8 |
| place, TD, RD, GRT(28), rt                |       6.348 |        0.01606 |        0.863  | -0.01411  |  0.01161 |            0.7 |
| place, TD, vCTS, CTS, rd, GRT(18), rt     |       6.906 |        0.01082 |        0.8798 | -0.008003 |  0.0101  |            0.6 |

## multiplier_top (macro array)

Ground truth flow runtime: 668 s.

Rung A explored 228 configurations.

6 front points across 0.024s to 65.9s. The widest gap (0.808) spans 0.024s to 14.4s and is structural rather than unexplored: it separates the configurations that skip placement from those that run it. Of 13 placed configurations timed here the fastest took 14.4s, so there is no cheap-but-placed estimate to be found in between -- the choice is binary.

| rungs                           |   runtime_s |   mean_rel_err |   kendall_tau |      bias |   spread |   worst_recall |
|:--------------------------------|------------:|---------------:|--------------:|----------:|---------:|---------------:|
| synth only                      |       0.024 |        0.2729  |        0.7073 | -0.2729   |  0.04208 |            0.1 |
| place, RD, CTS                  |      14.42  |        0.1504  |        0.7675 |  0.1349   |  0.08277 |            0.3 |
| place, TD, RD, vCTS, prop       |      21.15  |        0.05026 |        0.6562 | -0.04012  |  0.05995 |            0.2 |
| place, TD, RD, vCTS, CTS        |      29.28  |        0.04917 |        0.5143 | -0.007675 |  0.07096 |            0   |
| place, rd, GRT(1)               |      29.77  |        0.03718 |        0.7168 | -0.006053 |  0.06823 |            0.2 |
| place, place_ios, vCTS, CTS, rd |      65.94  |        0.03433 |        0.7287 | -0.0105   |  0.05078 |            0.1 |

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

