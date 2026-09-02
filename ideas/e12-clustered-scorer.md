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
| clustered **macro-cone** HPWL, 1 hop | +0.39 [-0.01, +0.72] | just misses |
| clustered **macro-cone** HPWL, 2 hops | +0.42 [-0.02, +0.73] | still misses, 2.3x the cost |

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

### That thread was pulled, and it does not lead anywhere

The obvious next move is to widen the cone: if aiming the sum at
macro-reachable nets bought +0.15 over full HPWL, aim it at more of
them. So the whole population was re-scored at 2 hops.

| | 1 hop | 2 hops |
|---|---|---|
| cone rho vs `macro_paths_mean` | +0.39 [-0.01, +0.72] | +0.42 [-0.02, +0.73] |
| full clustered HPWL rho | +0.26 [-0.22, +0.66] | +0.32 [-0.13, +0.68] |
| agreement with the flat rung | +0.66 [+0.34, +0.86] | +0.71 [+0.41, +0.89] |
| instances held out of clusters | 1458 | 2380 |
| nets in the cone | 2940 | 3923 |
| `gpl` time | 14.7 s | 34.4 s |
| cheaper than the flat rung by | 4.3x | 1.8x |

The point estimate moves by +0.02 and the interval still straddles zero,
so the second hop buys nothing that can be distinguished from noise --
while the cost more than doubles, because holding 922 more instances out
of the clusters is exactly what a coarsening rung must not do. At 2 hops
the rung has spent most of its speed advantage over the flat scorer and
bought no ranking with it.

Read together, the two rows say the cone was never close: +0.39 and
+0.42 are the same number at n=23, and the +0.01 shortfall at 1 hop was
a coincidence of where the interval fell, not a near miss to be closed
by tuning. **The macro-cone readout is not an underpowered version of a
working idea.** The remaining HPWL variants are the same scalar seen
through slightly different windows, and none of them has demonstrable
signal on this setup.

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

1. **Do not chase the cone.** That was this document's recommendation
   until the 2-hop re-score above was run; widening the cone costs 2.3x
   and buys +0.02, inside noise. Any further HPWL window is the same
   scalar reshaped, so a new rung has to leave the wirelength family --
   and `placement_cluster`'s point-masses rule out STA on a clustered
   placement, which is what makes this hard rather than merely unfinished.
2. **Re-derive E3 before building on it.** Raw HPWL did not rank here
   (+0.24, interval spanning zero) against a published +0.67.
3. **Do not reuse an archived score/truth pair to grade a re-run** unless
   the bazel-orfs pin is part of the recorded provenance -- see the
   negative findings in `docs/estimate.md`.
4. **Record infeasibility as an outcome.** One candidate could not be
   built at all (PDN could not repair a channel its macro placement
   created); no wirelength score can express that.
