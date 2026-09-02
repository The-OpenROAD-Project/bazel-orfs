# E12: the clustered global-place scorer, measured

Status: **run, and answered.** The result is not a pass or a fail on the
gate as written -- it relocates the problem.

## The question

RTL-MP already builds a physical hierarchy: std-cell clusters and
bundled nets, produced so its annealer has a tractable model. E12 asked
whether that hierarchy can double as the *scoring* netlist -- spread the
soft clusters around each candidate's fixed macros, read bundled-net
HPWL, and get a ranking-accurate score for an order of magnitude fewer
movables.

The appeal was that the clustering is already paid for, so the reduction
would be free and knob-free.

## What was built

Apparatus in ORFS `flow/test/macro_e12/` (see
[ORFS#4492](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/pull/4492),
kept as reproducible evidence): seeded candidate generation, the flat
control rung, RTL-MP's partition dumped once from the shared base
floorplan, the clustered rung, the production tail to grt as ground
truth, and a grader reporting Spearman rho with bootstrap intervals.

Nothing reimplements a field solver, deliberately: the thing being graded
has to be the solver that would ship. Both halves already exist --
`placement_cluster` makes N instances one movable, and
`rtl_macro_placer -keep_clustering_data` commits the partition to odb.

## The measurement

asap7/swerv_wrapper, 24 candidates generated, 23 evaluable, ground truth
measured through the full production tail on the same setup (~34 min per
candidate, ~1 h wall for all 23 at 4-way parallel).

| scorer | rho vs grt `macro_paths_mean` | |
|---|---|---|
| flat, **STA** aggregate | **+0.61 [+0.29, +0.78]** | ranks |
| flat, STA macro aggregate | +0.59 [+0.20, +0.80] | ranks |
| flat, raw HPWL | +0.24 [-0.24, +0.65] | no evidence |
| clustered HPWL | +0.26 [-0.22, +0.66] | no evidence |
| clustered **macro-cone** HPWL | +0.39 [-0.01, +0.72] | just misses |

Cost, same population: clustered 14.7 s and 0.87 GB against the flat
rung's 63.0 s and 2.43 GB. Agreement between the two on the same scalar:
rho +0.66 [+0.34, +0.86].

## What it means

**The clustering worked. The readout did not.**

The clustered rung reproduces the flat rung's HPWL faithfully (+0.66) at
roughly a quarter of the cost, and its ranking of the truth (+0.26) is
statistically indistinguishable from flat HPWL's (+0.24). So the
abstraction is not what costs the ranking -- it inherits a scalar that
carries no demonstrable signal on this setup. No refinement of the
cluster model can fix that.

E12's question therefore changes from *"how do we compute this number
more cheaply"* to *"which number should we compute"*.

**And the answer space is narrower than it looks.** `placement_cluster`
places every member instance at its cluster's centre, so a clustered
placement is a handful of point-masses; parasitics and STA taken off it
are meaningless. The clustered rung cannot carry an STA readout at all.
Whatever replaces HPWL has to live in the wirelength family.

That leaves exactly one live thread from this run: the **macro-cone**
readout at +0.39, best of the HPWL family and short of significance by
0.01. It is the only variant that moved toward the live KPI, and it did
so by restricting the sum to nets within reach of a macro pin -- i.e. by
aiming the score at the structure the KPI actually reads.

## Why the divergence was not a bug

At the pre-registered default the clustered solve diverges on this
design: overflow floors at 0.92 for 2175 iterations while the density
penalty climbs to 4.1e+28, then the step length goes Inf/NaN (GPL-0305).

That is a granularity mismatch, and both sides are behaving as intended:

- `BinGrid::initBins()` sizes bins from average **dbInst** area, correct
  for the regime `placement_cluster` was built for -- its commit
  describes "a small group of gates" whose members are "all placed at the
  center of the cluster", and notes that small clusters give better
  results.
- RTL-MP's clustering goes deliberately the other way:
  `min_num_macros_for_multilevel = 150` forces `max_level = 1` here, and
  `base_min_std_cell` targets 10183-50915 cells per cluster. Seven
  clusters end up holding 98.6% of the instances.

Neither tool is wrong; E12 straddles the seam. A smaller design
(nangate45/tinyRocket, 13 clusters) converges at the default, so it is
the granularity that diverges, not clustering as such. The swerv numbers
above therefore use `-bin_grid_count 8`, disclosed as a knob and treated
as exploratory rather than as a gate result.

## If someone picks this up

1. **Chase the cone, not the clusters.** Re-score at wider hop counts and
   with cone-only readouts. The truth is already measured, so each
   variant costs minutes.
2. **Re-derive E3 before building on it.** Raw HPWL did not rank here
   (+0.24, interval spanning zero) against a published +0.67.
3. **Do not reuse an archived score/truth pair to grade a re-run** unless
   the bazel-orfs pin is part of the recorded provenance -- see the
   negative findings in `docs/estimate.md`.
4. **Record infeasibility as an outcome.** One candidate could not be
   built at all (PDN could not repair a channel its macro placement
   created); no wirelength score can express that.
