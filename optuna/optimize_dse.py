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
from typing import List
import itertools

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


def find_workspace_root() -> str:
    """Find the Bazel workspace root directory.

    Returns BUILD_WORKSPACE_DIRECTORY env var (set by bazelisk run),
    otherwise falls back to current directory.
    """
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())


PARALLEL_RUNS = 8


def build_designs(
    trials: List[optuna.Trial],
    core_util: List[int],
    place_density: List[float],
    workspace_root: str,
    num_cores: List[int],
    pipeline_depth: List[int],
    work_per_stage: List[int],
) -> List[dict]:
    """Build design with given parameters and extract PPA metrics."""
    cmd = ["bazelisk", "build"] + list(
        itertools.chain.from_iterable(
            [
                [
                    f"--//optuna:density{i}={place_density[i]:.4f}",
                    f"--//optuna:utilization{i}={core_util[i]}",
                    f"--//optuna:params{i}=NUM_CORES {num_cores[i]} PIPELINE_DEPTH {pipeline_depth[i]} WORK_PER_STAGE {work_per_stage[i]}",
                    f"//optuna:mock-cpu_{i}_ppa",
                ]
                for i in range(len(trials))
            ]
        )
    )
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
        # beggars pruning, no multiobjective pruning in optuna.
        #
        # It has been discussed for years...
        #
        # https://github.com/optuna/optuna/issues/3450
        return [
            {
                "cell_area": 1e9,
                "power": 1e9,
                "frequency": 0.0,
            }
        ] * len(trials)

    metrics_list = []
    for i in range(len(trials)):
        # Parse PPA metrics - use absolute path from workspace root
        ppa_file = os.path.join(workspace_root, f"bazel-bin/optuna/mock-cpu_{i}_ppa.txt")
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

        compute = freq * num_cores[i] * work_per_stage[i]
        energy = power / freq

        metrics_list.append([metrics["cell_area"], compute / energy, compute])

        trials[i].set_user_attr("area", area)
        trials[i].set_user_attr("compute_per_energy", compute/energy)
        trials[i].set_user_attr("compute_per_time", compute)

    return metrics_list


def objective_multi(study : optuna.Study, trials: List[optuna.Trial], args, workspace_root: str) -> tuple:
    """Multi-objective: Minimize area and power."""
    core_util = []
    place_density = []
    num_cores = []
    pipeline_depth = []
    work_per_stage = []
    for trial in trials:
        core_util.append(
            trial.suggest_int("CORE_UTILIZATION", args.min_util, args.max_util)
        )
        place_density.append(
            trial.suggest_float("PLACE_DENSITY", args.min_density, args.max_density)
        )
        num_cores.append(trial.suggest_int("NUM_CORES", 1, 8))
        pipeline_depth.append(trial.suggest_int("PIPELINE_DEPTH", 1, 5))
        work_per_stage.append(trial.suggest_int("WORK_PER_STAGE", 1, 10))

    metrics = build_designs(
        trials,
        core_util,
        place_density,
        workspace_root,
        num_cores,
        pipeline_depth,
        work_per_stage,
    )

    # Store metrics
    for trial, metric in zip(trials, metrics):
        study.tell(trial, metric)


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
    for i in range(0, (args.n_trials + PARALLEL_RUNS - 1) // PARALLEL_RUNS):
        trials = [study.ask() for _ in range(min(PARALLEL_RUNS, args.n_trials - i))]

        objective_multi(study, trials, args, workspace_root)

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
                    f"area={trial.user_attrs['area']:.2f}",
                    f"compute_per_energy={trial.user_attrs['compute_per_energy']:.2f}",
                    f"compute_per_time={trial.user_attrs['compute_per_time']:.2f}",
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
