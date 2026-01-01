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
import logging

import optuna


def setup_logger(log_filename: str):
    """Set up a logger that writes to both a file and stdout."""
    logger = logging.getLogger("dse_logger")
    logger.setLevel(logging.INFO)
    # Remove any existing handlers
    logger.handlers.clear()
    # File handler
    fh = logging.FileHandler(log_filename)
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(message)s"))
    # Stream handler (stdout)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def find_workspace_root() -> str:
    """Find the Bazel workspace root directory.

    Returns BUILD_WORKSPACE_DIRECTORY env var (set by bazelisk run),
    otherwise falls back to current directory.
    """
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.getcwd())


# Number of parallel trials to run, a balance between speed and
# updating the Baysian sampler with new results.
PARALLEL_RUNS = 8


def build_designs(
    trials: List[optuna.Trial],
    core_util: List[int],
    place_density: List[float],
    workspace_root: str,
    num_cores: List[int],
    pipeline_depth: List[int],
    work_per_stage: List[int],
    rung: str,
) -> List[dict]:
    """Build design with given parameters and extract PPA metrics."""
    beggars_provisioning = ["--jobs", "1"] if rung != "synth" else []
    cmd = (
        ["bazelisk", "build", "--keep_going"]
        + beggars_provisioning
        + list(
            itertools.chain.from_iterable(
                [
                    [
                        f"--//optuna:density{i}={place_density[i]:.4f}",
                        f"--//optuna:utilization{i}={core_util[i]}",
                        f"--//optuna:params{i}=NUM_CORES {num_cores[i]} PIPELINE_DEPTH {pipeline_depth[i]} WORK_PER_STAGE {work_per_stage[i]}",
                        f"//optuna:mock-cpu_{i}_{rung}_ppa",
                    ]
                    for i in range(len(trials))
                ]
            )
        )
    )
    log.info(subprocess.list2cmdline(cmd))
    result = subprocess.run(
        cmd,
        cwd=workspace_root,  # Run in workspace root
    )

    if result.returncode != 0:
        print(f"❌ Build failed, looking for successful trials as we used --keep_going")

    metrics_list = []
    for i in range(len(trials)):
        # Parse PPA metrics - use absolute path from workspace root
        ppa_file = os.path.join(
            workspace_root, f"bazel-bin/optuna/mock-cpu_{i}_{rung}_ppa.txt"
        )
        metrics = {}
        if os.path.exists(ppa_file):
            with open(ppa_file) as f:
                for line in f:
                    if ":" in line and not line.startswith("#"):
                        key, value = line.split(":", 1)
                        metrics[key.strip()] = float(value.strip())
            area = metrics.get("cell_area", 1e9)
            power = metrics.get("estimated_power_uw", 1e9)
            freq = metrics.get("frequency_ghz", 0.0)
        else:
            print("Beggars pruning - optuna multiobjective pruning not supported")
            area = 1e9
            power = 1e9
            freq = 1000

        compute = freq * num_cores[i] * work_per_stage[i]
        energy = power / freq

        metrics_list.append([metrics["cell_area"], compute / energy, compute])

        trials[i].set_user_attr("area", area)
        trials[i].set_user_attr("compute_per_energy", compute / energy)
        trials[i].set_user_attr("compute_per_time", compute)
        log.info(
            f"CORE_UTILIZATION={core_util[i]}%, "
            f"PLACE_DENSITY={place_density[i]:.3f}, "
            f"NUM_CORES={num_cores[i]}, "
            f"PIPELINE_DEPTH={pipeline_depth[i]}, "
            f"WORK_PER_STAGE={work_per_stage[i]}"
        )
        log.info(
            f"AREA={area:.2f}, "
            f"COMPUTE/ENERGY={compute/energy:.2f}, "
            f"COMPUTE/TIME={compute:.2f}"
        )

    return metrics_list


def objective_multi(
    study: optuna.Study,
    trials: List[optuna.Trial],
    args,
    workspace_root: str,
    rung: str,
    previous_study: optuna.Study,
) -> tuple:
    """Multi-objective: Minimize area and power."""
    core_util = []
    place_density = []
    num_cores = []
    pipeline_depth = []
    work_per_stage = []

    # 1. SETUP: Warm-start if previous study exists
    if previous_study is not None:
        # Get the Top 5 Pareto optimal trials
        best_trials = previous_study.best_trials[:5]

        # Register (queue) them into the current study
        for t in best_trials:
            # This tells Optuna: "For the next trial, force these parameters"
            study.enqueue_trial(t.params)

    # 2. EXECUTION: Standard loop for ALL trials
    # Optuna automatically checks the queue first. If the queue has items (from step 1),
    # it uses them. If the queue is empty, it samples new values from the ranges below.
    for trial in trials:
        core_util.append(trial.suggest_int("CORE_UTILIZATION", 10, 90))
        place_density.append(trial.suggest_float("PLACE_DENSITY", 0.1, 0.9))
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
        rung,
    )

    # Store metrics
    for trial, metric in zip(trials, metrics):
        study.tell(trial, metric)


def main():
    parser = argparse.ArgumentParser(
        description="Optuna-based DSE for optimal CORE_UTILIZATION and PLACE_DENSITY"
    )
    parser.add_argument(
        "--trials", type=int, default=20, help="Number of trials (default: 20)"
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
    global log
    log_file_name = os.path.join(output_dir, "dse.log")
    log = setup_logger(log_file_name)

    print("=" * 70)
    print("Optuna DSE: Finding Optimal Design Parameters")
    print(f"Workspace root: {workspace_root}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Trials: {args.trials}, Seed: {args.seed}")
    print("=" * 70)

    storage_url = f"sqlite:///{os.path.join(workspace_root, "optuna/results/dse.db")}"
    print(f"Using storage: {storage_url}")

    previous_study = None
    for rung_number, rung in enumerate(["synth", "place", "grt"]):
        study = optuna.create_study(
            directions=["minimize", "maximize", "maximize"],  # Search for pareto front
            sampler=optuna.samplers.TPESampler(seed=args.seed),
            # storage=storage_url,
            load_if_exists=True,
        )
        keep_percent = 20
        trials_per_rung = max(args.trials // ((100 // keep_percent) ** rung_number), 1)
        log.info(f"Study {rung} with {trials_per_rung} trials")
        for i in range(
            0, (trials_per_rung + PARALLEL_RUNS - 1) // PARALLEL_RUNS, PARALLEL_RUNS
        ):
            trials = [
                study.ask() for _ in range(min(PARALLEL_RUNS, trials_per_rung - i))
            ]

            objective_multi(
                study,
                trials,
                args,
                workspace_root,
                rung,
                previous_study if i == 0 else None,
            )
        previous_study = study

    # Print results
    print(f"\n{'=' * 70}\nResults\n{'=' * 70}")

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

    print(f"Pareto optimal solutions: {len(study.best_trials)}")
    for i, trial in enumerate(study.best_trials):
        write_trial(sys.stdout, trial)

    plot_file = os.path.join(output_dir, "optuna_dse_results.html")
    fig = optuna.visualization.plot_pareto_front(
        study,
        target_names=["Area", "Compute/Power", "Compute/time"],
    )
    fig.write_html(plot_file)
    print(f"Log file saved to: {log_file_name}")
    print(f"Pareto front plot saved to: {plot_file}")


if __name__ == "__main__":
    main()
