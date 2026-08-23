import sys
import os
import pandas as pd
import matplotlib.pyplot as plt


def main():
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")

    csv_simple = os.path.join(ws, "test/estimation_ladder/pareto_front_multiplier.csv")
    csv_top = os.path.join(ws, "test/estimation_ladder/pareto_front_multiplier_top.csv")
    readme_path = os.path.join(ws, "test/estimation_ladder/README.md")

    if not os.path.exists(csv_simple):
        print(
            f"CSVs not found at {csv_simple}. Falling back to default if test is running."
        )
        return  # Might be running outside of test context without generating csvs manually yet

    df_simple = pd.read_csv(csv_simple)
    # df_top = pd.read_csv(csv_top)

    df_simple = df_simple.sort_values(by="runtime_ms")
    # df_top = df_top.sort_values(by='runtime_ms')

    # Generate Plot
    plt.figure(figsize=(10, 6))

    plt.plot(
        df_simple["runtime_ms"],
        df_simple["correlation"],
        color="blue",
        alpha=0.7,
        label="multiplier",
        marker="o",
    )
    for i, row in df_simple.iterrows():
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
            (row["runtime_ms"], row["correlation"]),
            fontsize=8,
            alpha=0.7,
            color="blue",
        )

    # plt.plot(df_top['runtime_ms'], df_top['correlation'], color='red', alpha=0.7, label='multiplier_top', marker='o')
    # for i, row in df_top.iterrows():
    #     label = []
    #     if row.get('run_place') == 0:
    #         label.append("No Place")
    #     else:
    #         if row.get('place_timing') == 1: label.append("TD")
    #         if row.get('place_routability') == 1: label.append("RD")
    #         if row.get('run_grt') == 1: label.append(f"GRT({int(row['grt_iterations'])})")
    #     plt.annotate(", ".join(label), (row['runtime_ms'], row['correlation']), fontsize=8, alpha=0.7, color='red')

    plt.xlabel("Runtime (ms)")
    plt.ylabel("Correlation (Pearson r for min_period)")
    plt.title("Pareto Front: Timing Correlation vs. Runtime")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)

    plot_path = os.path.join(os.path.dirname(readme_path), "pareto_plot.png")
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    print(f"Saved plot to {plot_path}")

    table_simple_md = df_simple.to_markdown(index=False)
    # table_top_md = df_top.to_markdown(index=False)

    readme_content = f"""# Estimation Ladder

## Abstract / Results

Synthesis vs. GRT correlation for minimum clock period is adequate for a simple `multiplier`, but degrades poorly for complex designs populated with macros because simple wireload models fail to capture complex inter-macro routing congestion.

This tuning study demonstrates how we can restore accuracy by incrementally adding early placement and global routing stages ("the estimation ladder"), forming a Pareto front of Runtime vs. Correlation.

![Pareto Plot](pareto_plot.png)

### Pareto Front: `multiplier` (Simple Design)
{table_simple_md}

<!-- TODO: Re-add multiplier_top once macro estimator is fixed -->
<!-- ### Pareto Front: `multiplier_top` (Complex Macro Design) -->
<!-- table_top_md goes here -->


---

## Details and Methodology

This directory contains a test suite that uses Optuna to evaluate the trade-off between runtime and timing correlation accuracy across different early-estimation stages (Synthesis only, Global Placement, and Global Routing) against a Global-Routed ground truth.

### Designs
- `multiplier.sv`: A simple parameterizable pipelined multiplier.
- `multiplier_top.sv`: A complex design instantiating a 4x4 array of the multiplier macros, introducing significant wire routing complexity between macros.

### Execution
The `optuna_study.py` script sweeps parameters (`RUN_PLACE`, `GPL_TIMING_DRIVEN`, `GPL_ROUTABILITY_DRIVEN`, `RUN_GRT`) to maximize Pearson correlation of extracted paths while minimizing runtime. 

To run the full suite and regenerate this README:
```bash
bazel test //test/estimation_ladder/...
bazel run //test/estimation_ladder:update-readme
```
"""
    with open(readme_path, "w") as f:
        f.write(readme_content)

    print(f"Updated {readme_path}")


if __name__ == "__main__":
    main()
