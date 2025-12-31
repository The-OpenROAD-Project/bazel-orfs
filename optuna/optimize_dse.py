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


def find_workspace_root() -> str:
    """Find the Bazel workspace root directory.

    Returns BUILD_WORKSPACE_DIRECTORY env var (set by bazelisk run),
    otherwise falls back to current directory.
    """
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())


def build_design(core_util: int, place_density: float, workspace_root: str) -> dict:
    """Build design with given parameters and extract PPA metrics."""
    print(
        f"\n{'=' * 70}\n"
        f"CORE_UTILIZATION = {core_util}%, PLACE_DENSITY = {place_density:.3f}\n"
        f"{'=' * 70}"
    )

    result = subprocess.run(
        [
            "bazelisk",
            "build",
            f"--define=CORE_UTILIZATION={core_util}",
            f"--define=PLACE_DENSITY={place_density:.4f}",
            "//optuna:mock-cpu_cts",
            "//optuna:mock-cpu_ppa",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=workspace_root,  # Run in workspace root
    )

    if result.returncode != 0:
        print(f"❌ Build failed")
        print(f"Error:\n{result.stderr[-800:]}")
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
    try:
        with open(ppa_file) as f:
            for line in f:
                if ":" in line and not line.startswith("#"):
                    key, value = line.split(":", 1)
                    metrics[key.strip()] = float(value.strip())
    except Exception as e:
        print(f"❌ Failed to parse PPA: {e}")
        return {
            "cell_area": 1e9,
            "power": 1e9,
            "slack": -1e9,
            "frequency": 0.0,
            "failed": True,
        }

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
        "failed": False,
    }


def objective_single(trial: optuna.Trial, args, workspace_root: str) -> float:
    """Single-objective: Minimize area."""
    core_util = trial.suggest_int("CORE_UTILIZATION", args.min_util, args.max_util)
    place_density = trial.suggest_float(
        "PLACE_DENSITY", args.min_density, args.max_density
    )

    metrics = build_design(core_util, place_density, workspace_root)

    # Store metrics
    trial.set_user_attr("area", metrics["cell_area"])
    trial.set_user_attr("power", metrics["power"])
    trial.set_user_attr("slack", metrics["slack"])
    trial.set_user_attr("frequency", metrics["frequency"])
    trial.set_user_attr("failed", metrics["failed"])

    return metrics["cell_area"]  # Minimize area


def objective_multi(trial: optuna.Trial, args, workspace_root: str) -> tuple:
    """Multi-objective: Minimize area and power."""
    core_util = trial.suggest_int("CORE_UTILIZATION", args.min_util, args.max_util)
    place_density = trial.suggest_float(
        "PLACE_DENSITY", args.min_density, args.max_density
    )

    metrics = build_design(core_util, place_density, workspace_root)

    # Store metrics
    trial.set_user_attr("area", metrics["cell_area"])
    trial.set_user_attr("power", metrics["power"])
    trial.set_user_attr("slack", metrics["slack"])
    trial.set_user_attr("frequency", metrics["frequency"])
    trial.set_user_attr("failed", metrics["failed"])

    return (metrics["cell_area"], metrics["power"])  # Minimize both


def constraints(trial: optuna.Trial) -> tuple:
    """Constraint: slack >= 0 (must meet timing)."""
    slack = trial.user_attrs.get("slack", -1e9)
    return (-slack,)  # Return -slack so constraint is satisfied when slack >= 0


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
        "--multi-objective",
        action="store_true",
        help="Use multi-objective optimization (area + power)",
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
    print(
        f"Mode: {'Multi-objective (Area+Power)' if args.multi_objective else 'Single-objective (Area)'}"
    )
    print("=" * 70)

    # Create study
    if args.multi_objective:
        study = optuna.create_study(
            directions=["minimize", "minimize"],  # Minimize area and power
            sampler=optuna.samplers.TPESampler(
                seed=args.seed, constraints_func=constraints
            ),
        )
        study.optimize(
            lambda trial: objective_multi(trial, args, workspace_root),
            n_trials=args.n_trials,
            show_progress_bar=True,
        )
    else:
        study = optuna.create_study(
            direction="minimize",  # Minimize area
            sampler=optuna.samplers.TPESampler(
                seed=args.seed, constraints_func=constraints
            ),
        )
        study.optimize(
            lambda trial: objective_single(trial, args, workspace_root),
            n_trials=args.n_trials,
            show_progress_bar=True,
        )

    # Print results
    print(f"\n{'=' * 70}\nResults\n{'=' * 70}")

    try:
        if args.multi_objective:
            print(f"Pareto optimal solutions: {len(study.best_trials)}")
            for i, trial in enumerate(study.best_trials[:5]):  # Show top 5
                print(f"\nSolution {i+1}:")
                print(f"  CORE_UTILIZATION: {trial.params['CORE_UTILIZATION']}%")
                print(f"  PLACE_DENSITY: {trial.params['PLACE_DENSITY']:.3f}")
                print(f"  Area: {trial.user_attrs['area']:.3f} um²")
                print(f"  Power: {trial.user_attrs['power']:.1f} uW")
                print(f"  Slack: {trial.user_attrs['slack']:.2f} ps")
        else:
            print(f"Best trial: {study.best_trial.number}")
            print(f"  CORE_UTILIZATION: {study.best_params['CORE_UTILIZATION']}%")
            print(f"  PLACE_DENSITY: {study.best_params['PLACE_DENSITY']:.3f}")
            print(f"  Best area: {study.best_value:.3f} um²")
            print(f"  Power: {study.best_trial.user_attrs['power']:.1f} uW")
            print(f"  Slack: {study.best_trial.user_attrs['slack']:.2f} ps")
    except ValueError:
        print("\n⚠️  No feasible trials completed!")
        print("All trials either failed to build or violated timing constraints.")
        print("\nSuggestions:")
        print("  - Relax timing constraints (increase clock period)")
        print("  - Adjust parameter ranges")
        print("  - Check build logs for errors")
        return

    # Save results
    results_file = os.path.join(output_dir, "optuna_dse_results.txt")
    with open(results_file, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("Optuna DSE Results\n")
        f.write("=" * 70 + "\n\n")

        if args.multi_objective:
            f.write(f"Pareto optimal solutions: {len(study.best_trials)}\n\n")
            for i, trial in enumerate(study.best_trials):
                f.write(f"Solution {i+1}:\n")
                f.write(f"  CORE_UTIL={trial.params['CORE_UTILIZATION']}%, ")
                f.write(f"PLACE_DENSITY={trial.params['PLACE_DENSITY']:.3f}, ")
                f.write(f"Area={trial.user_attrs['area']:.3f}um², ")
                f.write(f"Power={trial.user_attrs['power']:.1f}uW, ")
                f.write(f"Slack={trial.user_attrs['slack']:.2f}ps\n")
        else:
            f.write(f"Best solution:\n")
            f.write(f"  CORE_UTIL={study.best_params['CORE_UTILIZATION']}%, ")
            f.write(f"PLACE_DENSITY={study.best_params['PLACE_DENSITY']:.3f}\n")
            f.write(f"  Area={study.best_value:.3f}um², ")
            f.write(f"Power={study.best_trial.user_attrs['power']:.1f}uW, ")
            f.write(f"Slack={study.best_trial.user_attrs['slack']:.2f}ps\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("All Feasible Trials:\n")
        f.write("=" * 70 + "\n")
        for trial in study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                slack = trial.user_attrs.get("slack", -1e9)
                if slack >= 0:
                    f.write(
                        f"Trial {trial.number}: "
                        f"UTIL={trial.params['CORE_UTILIZATION']}%, "
                        f"DENS={trial.params['PLACE_DENSITY']:.3f}, "
                        f"Area={trial.user_attrs['area']:.2f}um², "
                        f"Power={trial.user_attrs['power']:.1f}uW\n"
                    )

    print(f"\n✓ Results saved to {os.path.abspath(results_file)}")

    # Generate plots
    plot_file = os.path.join(output_dir, "optuna_dse_results.pdf")
    plot_results(study, args.multi_objective, plot_file)


if __name__ == "__main__":
    main()
