# Estimation Ladder

## Abstract / Results

How accurately can early flow stages estimate the minimum clock period of the
near-critical reg2reg paths, compared to a global-routed ground truth — and at
what runtime cost?

Synthesis-only timing is optimistic: it sees no wires. Incrementally adding
early placement and global routing stages ("the estimation ladder") buys back
accuracy at increasing runtime, forming a Pareto front of runtime vs. mean
relative error of the estimated minimum clock period.

All runtimes measure the same thing: how long from the post-synthesis
netlist (`1_synth.odb`/`.sdc`) until a timing signal is available. For the
estimator rungs that is the estimator script itself; for the ground truth it
is the full floorplan-through-global-route flow, summed from the stage logs
and marked by the dashed lines.

![Pareto Plot](pareto_plot.png)

### Pareto Front: `multiplier` (Simple Design)
|   mean_rel_err |   runtime_s |   run_place |   place_timing |   place_routability |   run_grt |   grt_iterations |
|---------------:|------------:|------------:|---------------:|--------------------:|----------:|-----------------:|
|      0.210289  |       0.021 |           0 |            nan |                 nan |       nan |              nan |
|      0.063869  |       8.362 |           1 |              0 |                   1 |         1 |                2 |
|      0.0540325 |      20.581 |           1 |              1 |                   0 |         1 |                1 |

Ground truth flow runtime: 47 s.

### Pareto Front: `multiplier_top` (Complex Macro Design)
|   mean_rel_err |   runtime_s |   run_place |   place_timing |   place_routability |   run_grt |   grt_iterations |
|---------------:|------------:|------------:|---------------:|--------------------:|----------:|-----------------:|
|      0.300314  |      59.799 |           0 |            nan |                 nan |       nan |              nan |
|      0.0780001 |     178.172 |           1 |              0 |                   1 |         0 |              nan |
|      0.0591525 |     198.203 |           1 |              0 |                   1 |         1 |                1 |

Ground truth flow runtime: 582 s.

### Scope

This is a mock-study of an estimator script to exercise the bazel-orfs
infrastructure: the designs are complicated enough to exercise the full
use-case — macros, abstracts, reg2reg paths ending in macro pins, a
ground-truth flow, and an Optuna sweep driving a fast estimator executable —
while executing as quickly as possible. They are deliberately not big and
complicated enough to be interesting as an estimation study in their own
right: the designs are small and wire-poor, so routing congestion does not
drive timing here.

### Further study

A design with hundreds of memory macros, such as MegaBoom, is where this
method would get interesting. On such a design the near-critical paths cross
between macros, and their delay is dominated by wires whose lengths do not
exist until macros are placed: synthesis-only timing would not merely be
optimistic, it would mis-rank paths, because it cannot see which macros end
up far apart. The gap between the ladder rungs should widen accordingly, and
new effects become first-order that these small designs cannot exhibit:

- Macro placement quality (halos, channel widths, RTLMP parameters)
  determines the wire lengths that dominate timing, so the estimation
  ladder's accuracy becomes a direct function of how production-like the
  early macro placement is.
- Routing congestion in the channels between macros separates global
  placement estimates from global routing estimates: detours around
  congested channels are exactly what `estimate_parasitics -placement`
  cannot see and `-global_routing` can.
- Each rung's runtime grows into real money — macro placement and global
  routing on a MegaBoom-class design take tens of minutes to hours — so the
  runtime/accuracy Pareto front stops being a curiosity and becomes an
  engineering decision: which rung is cheap enough for an RTL iteration
  loop, and which is needed before committing to a full flow run?

The method transfers directly: the ground truth sampling (reg2reg paths,
where a "register" endpoint can be a macro), the mean-relative-error metric,
and the Optuna sweep are all design-agnostic. What changes is the answer —
and on a macro-dominated design, the interesting question becomes which
rung of the ladder is the cheapest one that still ranks and sizes the
near-critical paths correctly.

---

## Details and Methodology

This directory contains a test suite that uses Optuna to evaluate the
trade-off between runtime and timing estimation accuracy across different
early-estimation stages (Synthesis only, Global Placement, and Global Routing)
against a Global-Routed ground truth.

The ground truth (`extract.tcl`) samples up to 100 unique paths from the
`reg2reg` path group (note: a "register" can be a macro, not just a
flip-flop): the worst 25% of the minimum-period range, split into 10 buckets
of up to 10 paths each. It also reports the runtime of the flow that produced
the grt ODB (floorplan through global route, summed from the stage logs;
synthesis is excluded as the common starting point of both the ground truth
and the estimator). The estimator (`estimator.tcl`) must measure every
sampled path — a path it cannot find is an error, not a fallback.

The accuracy metric is the mean relative error of the estimated minimum clock
period over the sampled paths, |estimate - truth| / truth.

### Designs
- `multiplier.sv`: A simple parameterizable pipelined multiplier.
- `multiplier_top.sv`: A complex design instantiating a 4x4 array of the multiplier macros, introducing significant wire routing complexity between macros.

### Execution
The `optuna_study.py` script sweeps parameters (`RUN_PLACE`, `GPL_TIMING_DRIVEN`, `GPL_ROUTABILITY_DRIVEN`, `RUN_GRT`) to minimize mean relative error of estimated minimum clock period while minimizing runtime.

To run the full suite and regenerate this README:
```bash
bazel test //test/estimation_ladder/...
bazel run //test/estimation_ladder:optuna_study
bazel run //test/estimation_ladder:optuna_study_top
bazel run //test/estimation_ladder:update-readme
```
