import sys
import os
import json
import pandas as pd
import matplotlib.pyplot as plt


def annotate(df, color):
    for _, row in df.iterrows():
        label = []
        if row.get("run_place") == 0:
            label.append("No Place")
        else:
            if row.get("place_timing") == 1:
                label.append("TD")
            if row.get("place_routability") == 1:
                label.append("RD")
            if row.get("run_grt") == 1:
                label.append(f"GRT({int(row['grt_iterations'])})")
        plt.annotate(
            ", ".join(label),
            (row["runtime_s"], row["mean_rel_err"]),
            fontsize=8,
            alpha=0.7,
            color=color,
        )


def main():
    if len(sys.argv) < 3:
        sys.exit("Usage: update_readme.py <ground_truth_json> <ground_truth_top_json>")

    with open(sys.argv[1]) as f:
        gt_runtime_s = json.load(f)["runtime_s"]
    with open(sys.argv[2]) as f:
        gt_top_runtime_s = json.load(f)["runtime_s"]

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")

    csv_simple = os.path.join(ws, "test/estimation_ladder/pareto_front_multiplier.csv")
    csv_top = os.path.join(ws, "test/estimation_ladder/pareto_front_multiplier_top.csv")
    readme_path = os.path.join(ws, "test/estimation_ladder/README.md")

    df_simple = pd.read_csv(csv_simple).sort_values(by="runtime_s")
    df_top = pd.read_csv(csv_top).sort_values(by="runtime_s")

    # Generate Plot
    plt.figure(figsize=(10, 6))

    plt.plot(
        df_simple["runtime_s"],
        df_simple["mean_rel_err"],
        color="blue",
        alpha=0.7,
        label="multiplier",
        marker="o",
    )
    annotate(df_simple, "blue")

    plt.plot(
        df_top["runtime_s"],
        df_top["mean_rel_err"],
        color="red",
        alpha=0.7,
        label="multiplier_top",
        marker="o",
    )
    annotate(df_top, "red")

    plt.axvline(
        gt_runtime_s,
        color="blue",
        linestyle="--",
        alpha=0.5,
        label=f"multiplier ground truth flow ({gt_runtime_s:.0f} s)",
    )
    plt.axvline(
        gt_top_runtime_s,
        color="red",
        linestyle="--",
        alpha=0.5,
        label=f"multiplier_top ground truth flow ({gt_top_runtime_s:.0f} s)",
    )

    # The estimator rungs and the ground truth flows span several decades
    # (tens of milliseconds to about ten minutes): log scale keeps them
    # all legible on one axis.
    plt.xscale("log")
    plt.xlabel("Runtime (s, log scale)")
    plt.ylabel("Mean relative error of min clock period (lower is better)")
    plt.title("Pareto Front: Estimation Accuracy vs. Runtime")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)

    plot_path = os.path.join(os.path.dirname(readme_path), "pareto_plot.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    print(f"Saved plot to {plot_path}")

    table_simple_md = df_simple.to_markdown(index=False)
    table_top_md = df_top.to_markdown(index=False)

    readme_content = f"""# Estimation Ladder

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
{table_simple_md}

Ground truth flow runtime: {gt_runtime_s:.0f} s.

### Pareto Front: `multiplier_top` (Complex Macro Design)
{table_top_md}

Ground truth flow runtime: {gt_top_runtime_s:.0f} s.

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
"""
    with open(readme_path, "w") as f:
        f.write(readme_content)

    print(f"Updated {readme_path}")


if __name__ == "__main__":
    main()
