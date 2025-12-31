#!/usr/bin/env python3
"""
Optuna-based Design Space Exploration for IC designs.

Objective: Find optimal CORE_UTILIZATION and PLACE_DENSITY that minimize
          area (and optionally power) while meeting timing constraints.

Experimental Setup:
  - Fixed clock frequency (constraint)
  - Variable design parameters: CORE_UTILIZATION, PLACE_DENSITY
  - Constraint: Design must meet timing (slack >= 0)
  - Objective: Minimize area (single-objective) or area+power (multi-objective)
"""

import argparse
import os
import subprocess
import sys


import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import optuna

# Fix import for Bazel py_binary: add script dir to sys.path
sys.path.insert(0, os.path.dirname(__file__))
from plot_results import plot_results


import matplotlib.pyplot as plt
from optuna.visualization.matplotlib import plot_pareto_front
import pandas


def save_pareto_pdf(study, filename="pareto_front.pdf", target_names=None):
    """
    Generates a Pareto Front plot for a multi-objective study and saves it as a PDF.

    Args:
        study: The Optuna study object.
        filename (str): The path/name of the output PDF file.
        target_names (list): Optional list of names for the objectives (e.g., ["Accuracy", "Latency"]).
    """
    # 1. Create the figure using the Matplotlib backend
    # Note: We assign the result to 'ax' (axes), though Optuna handles the drawing directly on the current figure.
    ax = plot_pareto_front(study, target_names=target_names)

    # 2. Tweak the layout to prevent labels from being cut off
    plt.tight_layout()

    # 3. Save the figure
    plt.savefig(filename, format="pdf", dpi=300)

    # 4. Close the plot to free up memory
    plt.close()

    print(f"Successfully saved plot to {filename}")


from pandas.plotting import parallel_coordinates

import pandas as pd
import matplotlib.pyplot as plt
from pandas.plotting import parallel_coordinates


def save_parallel_coords_pdf(study, objective_names, filename="parallel_coords.pdf"):
    df = study.trials_dataframe()
    df = df[df["state"] == "COMPLETE"]

    # 1. Select Parameters and Objectives
    param_cols = [c for c in df.columns if c.startswith("params_")]
    obj_cols = ["values_0", "values_1", "values_2"]

    subset = df[param_cols + obj_cols].copy()

    # 2. Rename columns
    clean_param_names = {c: c.replace("params_", "") for c in param_cols}
    subset = subset.rename(columns=clean_param_names)
    rename_objs = {k: v for k, v in zip(obj_cols, objective_names)}
    subset = subset.rename(columns=rename_objs)

    # 3. Create "Score" column robustly
    # We use the first objective (e.g., Area) to color the lines
    first_obj = subset[objective_names[0]]

    if first_obj.nunique() <= 1:
        # Fallback: If all results are identical, assign a single label
        subset["Score"] = "Converged"
    else:
        # FIX: Use pd.cut instead of pd.qcut
        # pd.cut creates bins based on value RANGE, not frequency, avoiding the "unique edges" error
        subset["Score"] = pd.cut(
            first_obj,
            bins=4,
            labels=["Best", "Good", "Avg", "Poor"],
            include_lowest=True,
        )

    # 4. Plot
    plt.figure(figsize=(12, 6))

    # Use a colormap that handles discrete labels well
    parallel_coordinates(subset, "Score", colormap="viridis", alpha=0.5)

    plt.title("Parameter Impact on Objectives")
    plt.ylabel("Value")
    plt.xticks(rotation=45)
    plt.grid(True, axis="x")
    plt.tight_layout()

    plt.savefig(filename, format="pdf")
    plt.close()
    print(f"✅ Parallel coords saved to: {filename}")


def find_workspace_root() -> str:
    """Find the Bazel workspace root directory.

    Returns BUILD_WORKSPACE_DIRECTORY env var (set by bazelisk run),
    otherwise falls back to current directory.
    """
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())


def build_design(
    core_util: int,
    place_density: float,
    workspace_root: str,
    num_cores: int,
    pipeline_depth: int,
    work_per_stage: int,
) -> dict:
    """Build design with given parameters and extract PPA metrics."""
    cmd = [
        "bazelisk",
        "build",
        f"--define=CORE_UTILIZATION={core_util}",
        f"--define=PLACE_DENSITY={place_density:.4f}",
        f"--define=VERILOG_TOP_PARAMS=NUM_CORES {num_cores} PIPELINE_DEPTH {pipeline_depth} WORK_PER_STAGE {work_per_stage}",
        "//optuna:mock-cpu_ppa",
    ]
    print(subprocess.list2cmdline(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=workspace_root,  # Run in workspace root
    )

    if result.returncode != 0:
        print(f"❌ Build failed")
        print(f"Error:\n{result.stderr[-800:]}")
        # beggars pruning
        return {
            "cell_area": 1e9,
            "power": 1e9,
            "slack": -1e9,
            "frequency": 0.0,
            "failed": True,
        }

    # Parse PPA metrics - use absolute path from workspace root
    ppa_file = os.path.join(workspace_root, "bazel-bin/optuna/mock-cpu_ppa.txt")
    metrics = {}
    with open(ppa_file) as f:
        for line in f:
            if ":" in line and not line.startswith("#"):
                key, value = line.split(":", 1)
                metrics[key.strip()] = float(value.strip())

    area = metrics.get("cell_area", 1e9)
    power = metrics.get("estimated_power_uw", 1e9)
    slack = metrics.get("slack", -1e9)
    freq = metrics.get("frequency_ghz", 0.0)

    meets_timing = slack >= 0
    print(f"{'✓' if meets_timing else '✗'} Slack: {slack:.2f} ps")
    print(f"  Area: {area:.3f} um², Power: {power:.1f} uW, Freq: {freq:.2f} GHz")

    return {
        "cell_area": area,
        "power": power,
        "slack": slack,
        "frequency": freq,
        "compute": freq,
        "failed": False,
    }


def objective_multi(trial: optuna.Trial, args, workspace_root: str) -> tuple:
    """Multi-objective: Minimize area and power."""
    core_util = trial.suggest_int("CORE_UTILIZATION", args.min_util, args.max_util)
    place_density = trial.suggest_float(
        "PLACE_DENSITY", args.min_density, args.max_density
    )
    num_cores = trial.suggest_int("NUM_CORES", 1, 8)
    pipeline_depth = trial.suggest_int("PIPELINE_DEPTH", 1, 5)
    work_per_stage = trial.suggest_int("WORK_PER_STAGE", 1, 10)

    metrics = build_design(
        core_util,
        place_density,
        workspace_root,
        num_cores,
        pipeline_depth,
        work_per_stage,
    )

    # Store metrics
    trial.set_user_attr("area", metrics["cell_area"])
    trial.set_user_attr("power", metrics["power"])
    trial.set_user_attr("slack", metrics["slack"])
    trial.set_user_attr("frequency", metrics["frequency"])
    trial.set_user_attr("failed", metrics["failed"])
    trial.set_user_attr("compute", metrics["frequency"] * num_cores * work_per_stage)

    return (
        metrics["cell_area"],
        metrics["compute"] / metrics["power"],
        metrics["compute"],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Optuna-based DSE for optimal CORE_UTILIZATION and PLACE_DENSITY"
    )
    parser.add_argument(
        "--min-util",
        type=int,
        default=30,
        help="Minimum CORE_UTILIZATION %% (default: 30)",
    )
    parser.add_argument(
        "--max-util",
        type=int,
        default=70,
        help="Maximum CORE_UTILIZATION %% (default: 70)",
    )
    parser.add_argument(
        "--min-density",
        type=float,
        default=0.20,
        help="Minimum PLACE_DENSITY (default: 0.20)",
    )
    parser.add_argument(
        "--max-density",
        type=float,
        default=0.70,
        help="Maximum PLACE_DENSITY (default: 0.70)",
    )
    parser.add_argument(
        "--n-trials", type=int, default=20, help="Number of trials (default: 20)"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (default: 42)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="optuna/results",
        help="Output directory for results (default: optuna/results)",
    )
    args = parser.parse_args()

    # Find workspace root directory
    workspace_root = find_workspace_root()

    # Create output directory if it doesn't exist
    # Use absolute path from workspace root
    output_dir = args.output_dir
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(workspace_root, output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 70)
    print("Optuna DSE: Finding Optimal Design Parameters")
    print(f"Workspace root: {workspace_root}")
    print(f"Working directory: {os.getcwd()}")
    print(f"CORE_UTILIZATION range: {args.min_util}% - {args.max_util}%")
    print(f"PLACE_DENSITY range: {args.min_density:.2f} - {args.max_density:.2f}")
    print(f"Trials: {args.n_trials}, Seed: {args.seed}")
    print("=" * 70)

    storage_url = f"sqlite:///{os.path.join(workspace_root, "optuna/results/dse.db")}"
    print(f"Using storage: {storage_url}")

    study = optuna.create_study(
        directions=["minimize", "maximize", "maximize"],  # Search for pareto front
        sampler=optuna.samplers.TPESampler(seed=args.seed),
        # storage=storage_url,
        load_if_exists=True,
    )
    study.optimize(
        lambda trial: objective_multi(trial, args, workspace_root),
        n_trials=args.n_trials,
        show_progress_bar=True,
    )

    # Print results
    print(f"\n{'=' * 70}\nResults\n{'=' * 70}")

    print(f"Pareto optimal solutions: {len(study.best_trials)}")
    if len(study.best_trials) == 0:
        print("\n⚠️  No feasible trials completed!")
        print("All trials either failed to build or violated timing constraints.")
        print("\nSuggestions:")
        print("  - Relax timing constraints (increase clock period)")
        print("  - Adjust parameter ranges")
        print("  - Check build logs for errors")
        return

    def write_trial(f, trial):
        f.write(
            ", ".join(
                [
                    f"CORE_UTILIZATION={trial.params['CORE_UTILIZATION']}%",
                    f"PLACE_DENSITY={trial.params['PLACE_DENSITY']:.3f}",
                    f"NUM_CORES={trial.params['NUM_CORES']}",
                    f"PIPELINE_DEPTH={trial.params['PIPELINE_DEPTH']}",
                    f"WORK_PER_STAGE={trial.params['WORK_PER_STAGE']}",
                    f"Area={trial.user_attrs['area']:.2f}um²",
                    f"Power={trial.user_attrs['power']:.1f}",
                    f"Compute={trial.user_attrs['compute']}",
                ]
            )
            + "\n"
        )

    for i, trial in enumerate(study.best_trials[:5]):  # Show top 5
        print(f"\nSolution {i+1}:")
        write_trial(sys.stdout, trial)

    plot_file = os.path.join(output_dir, "optuna_dse_results.html")
    fig = optuna.visualization.plot_pareto_front(
        study,
        target_names=["Area", "Compute/Power", "Compute/time"],
        include_dominated_trials=True,
    )
    fig.write_html(plot_file)
    print(f"✅ Pareto front plot saved to: {plot_file}")


if __name__ == "__main__":
    main()
