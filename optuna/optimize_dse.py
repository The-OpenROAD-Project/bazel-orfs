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
            "//optuna:lb_32x128_cts",
            "//optuna:lb_32x128_ppa",
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
    ppa_file = os.path.join(workspace_root, "bazel-bin/optuna/lb_32x128_ppa.txt")
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


def plot_results(study: optuna.Study, multi_objective: bool, output_file: str):
    """Generate optimization result plots with enhanced visualization."""
    # Collect data - separate normal and failed trials
    trials_data = []
    failed_trials = []
    for trial in study.trials:
        if trial.state == optuna.trial.TrialState.COMPLETE:
            trial_info = {
                "number": trial.number,
                "core_util": trial.params["CORE_UTILIZATION"],
                "place_density": trial.params["PLACE_DENSITY"],
                "area": trial.user_attrs.get("area", 0),
                "power": trial.user_attrs.get("power", 0),
                "slack": trial.user_attrs.get("slack", -1e9),
                "meets_timing": trial.user_attrs.get("slack", -1e9) >= 0,
            }
            # Separate failed builds from normal ones
            if trial.user_attrs.get("failed", False):
                failed_trials.append(trial_info)
            else:
                trials_data.append(trial_info)

    if not trials_data:
        print("⚠ No completed trials to plot")
        return

    feasible = [t for t in trials_data if t["meets_timing"]]
    infeasible = [t for t in trials_data if not t["meets_timing"]]

    # Set publication-quality style
    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.labelsize": 13,
            "axes.titlesize": 14,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 11,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "font.family": "sans-serif",
            "axes.grid": True,
            "grid.alpha": 0.3,
            "grid.linestyle": "--",
        }
    )

    with PdfPages(output_file) as pdf:
        # Plot 1: CORE_UTILIZATION vs Area (colored by Power)
        fig, ax = plt.subplots(figsize=(11, 7))

        if feasible:
            core_utils = [t["core_util"] for t in feasible]
            areas = [t["area"] for t in feasible]
            powers = [t["power"] for t in feasible]

            # Scatter plot with power as color
            scatter = ax.scatter(
                core_utils,
                areas,
                c=powers,
                cmap="plasma",
                s=250,
                alpha=0.8,
                edgecolors="black",
                linewidth=1.5,
                marker="o",
                zorder=3,
            )

            # Add trend line if enough points
            if len(core_utils) > 2:
                z = np.polyfit(core_utils, areas, 2)
                p = np.poly1d(z)
                x_trend = np.linspace(min(core_utils), max(core_utils), 100)
                ax.plot(
                    x_trend,
                    p(x_trend),
                    "b--",
                    linewidth=2,
                    alpha=0.5,
                    label="Trend (2nd order)",
                    zorder=2,
                )

            # Highlight best area point
            best_idx = areas.index(min(areas))
            ax.scatter(
                [core_utils[best_idx]],
                [areas[best_idx]],
                c="green",
                s=500,
                alpha=1.0,
                edgecolors="black",
                linewidth=3,
                marker="*",
                label="Lowest Area",
                zorder=5,
            )

            # Annotate best point
            ax.annotate(
                f"UTIL={core_utils[best_idx]}%\nArea={areas[best_idx]:.3f}um²\nPower={powers[best_idx]:.1f}uW",
                xy=(core_utils[best_idx], areas[best_idx]),
                xytext=(15, -15),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.6", fc="lightgreen", alpha=0.9),
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.3", lw=2),
                fontsize=9,
                fontweight="bold",
            )

            # Colorbar
            cbar = plt.colorbar(scatter, ax=ax, pad=0.02)
            cbar.set_label("Power (uW)", fontsize=12, fontweight="bold")
            cbar.ax.tick_params(labelsize=10)

        if infeasible:
            ax.scatter(
                [t["core_util"] for t in infeasible],
                [t["area"] for t in infeasible],
                c="gray",
                s=150,
                alpha=0.4,
                edgecolors="red",
                linewidth=2,
                label="Timing Violation",
                marker="x",
                zorder=1,
            )

        # Add failed builds at the top of the plot
        if failed_trials:
            y_max = ax.get_ylim()[1]
            ax.scatter(
                [t["core_util"] for t in failed_trials],
                [y_max * 0.95] * len(failed_trials),  # Position near top
                c="red",
                s=300,
                alpha=0.8,
                edgecolors="darkred",
                linewidth=2,
                label=f"Build Failed ({len(failed_trials)})",
                marker="X",
                zorder=10,
            )

        ax.set_xlabel("CORE_UTILIZATION (%)", fontsize=14, fontweight="bold")
        ax.set_ylabel("Cell Area (um²)", fontsize=14, fontweight="bold")
        title = "Core Utilization vs Area (Color = Power)"
        if failed_trials:
            title += f"\n({len(failed_trials)} builds failed - shown as red X at top)"
        ax.set_title(title, fontsize=16, fontweight="bold", pad=15)
        ax.legend(loc="best", fontsize=11, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle="--")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight", dpi=300)
        plt.close()

        # Plot 2: PLACE_DENSITY vs Area (colored by Power)
        fig, ax = plt.subplots(figsize=(11, 7))

        if feasible:
            densities = [t["place_density"] for t in feasible]
            areas = [t["area"] for t in feasible]
            powers = [t["power"] for t in feasible]

            # Scatter plot with power as color
            scatter = ax.scatter(
                densities,
                areas,
                c=powers,
                cmap="plasma",
                s=250,
                alpha=0.8,
                edgecolors="black",
                linewidth=1.5,
                marker="o",
                zorder=3,
            )

            # Add trend line
            if len(densities) > 2:
                z = np.polyfit(densities, areas, 2)
                p = np.poly1d(z)
                x_trend = np.linspace(min(densities), max(densities), 100)
                ax.plot(
                    x_trend,
                    p(x_trend),
                    "b--",
                    linewidth=2,
                    alpha=0.5,
                    label="Trend",
                    zorder=2,
                )

            # Highlight best area point
            best_idx = areas.index(min(areas))
            ax.scatter(
                [densities[best_idx]],
                [areas[best_idx]],
                c="green",
                s=500,
                alpha=1.0,
                edgecolors="black",
                linewidth=3,
                marker="*",
                label="Lowest Area",
                zorder=5,
            )

            # Annotate best
            ax.annotate(
                f"Density={densities[best_idx]:.3f}\nArea={areas[best_idx]:.3f}um²\nPower={powers[best_idx]:.1f}uW",
                xy=(densities[best_idx], areas[best_idx]),
                xytext=(15, -15),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.6", fc="lightgreen", alpha=0.9),
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.3", lw=2),
                fontsize=9,
                fontweight="bold",
            )

            # Colorbar
            cbar = plt.colorbar(scatter, ax=ax, pad=0.02)
            cbar.set_label("Power (uW)", fontsize=12, fontweight="bold")
            cbar.ax.tick_params(labelsize=10)

        if infeasible:
            ax.scatter(
                [t["place_density"] for t in infeasible],
                [t["area"] for t in infeasible],
                c="gray",
                s=150,
                alpha=0.4,
                edgecolors="red",
                linewidth=2,
                label="Timing Violation",
                marker="x",
                zorder=1,
            )

        # Add failed builds at the top of the plot
        if failed_trials:
            y_max = ax.get_ylim()[1]
            ax.scatter(
                [t["place_density"] for t in failed_trials],
                [y_max * 0.95] * len(failed_trials),  # Position near top
                c="red",
                s=300,
                alpha=0.8,
                edgecolors="darkred",
                linewidth=2,
                label=f"Build Failed ({len(failed_trials)})",
                marker="X",
                zorder=10,
            )

        ax.set_xlabel("PLACE_DENSITY", fontsize=14, fontweight="bold")
        ax.set_ylabel("Cell Area (um²)", fontsize=14, fontweight="bold")
        title = "Placement Density vs Area (Color = Power)"
        if failed_trials:
            title += f"\n({len(failed_trials)} builds failed - shown as red X at top)"
        ax.set_title(title, fontsize=16, fontweight="bold", pad=15)
        ax.legend(loc="best", fontsize=11, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle="--")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight", dpi=300)
        plt.close()

        # Plot 3: Area vs Power Pareto Frontier (enhanced for multi-objective)
        if multi_objective and feasible:
            fig, ax = plt.subplots(figsize=(11, 8))

            # Get Pareto optimal points
            pareto_trials = study.best_trials if hasattr(study, "best_trials") else []
            pareto_areas = [t.user_attrs.get("area", 0) for t in pareto_trials]
            pareto_powers = [t.user_attrs.get("power", 0) for t in pareto_trials]

            all_areas = [t["area"] for t in feasible]
            all_powers = [t["power"] for t in feasible]

            # Plot all feasible points
            ax.scatter(
                all_areas,
                all_powers,
                c="lightblue",
                s=180,
                alpha=0.5,
                edgecolors="gray",
                linewidth=1,
                label=f"Feasible ({len(feasible)} points)",
                marker="o",
                zorder=2,
            )

            # Highlight Pareto optimal points
            if pareto_areas:
                ax.scatter(
                    pareto_areas,
                    pareto_powers,
                    c="red",
                    s=400,
                    alpha=0.95,
                    edgecolors="black",
                    linewidth=2.5,
                    label=f"Pareto Optimal ({len(pareto_areas)})",
                    marker="*",
                    zorder=10,
                )

                # Draw Pareto curve
                sorted_idx = np.argsort(pareto_areas)
                sorted_areas = [pareto_areas[i] for i in sorted_idx]
                sorted_powers = [pareto_powers[i] for i in sorted_idx]
                ax.plot(
                    sorted_areas,
                    sorted_powers,
                    "r--",
                    linewidth=2.5,
                    alpha=0.7,
                    label="Pareto Front",
                    zorder=8,
                )

                # Annotate Pareto points
                for i, (a, p) in enumerate(zip(pareto_areas, pareto_powers)):
                    ax.annotate(
                        f"{i+1}",
                        xy=(a, p),
                        xytext=(5, 5),
                        textcoords="offset points",
                        fontsize=9,
                        fontweight="bold",
                        color="white",
                        bbox=dict(
                            boxstyle="circle,pad=0.3", fc="red", ec="black", lw=1.5
                        ),
                    )

                # Add dominated region shading
                if len(pareto_areas) > 1:
                    min_area, max_area = min(pareto_areas), max(pareto_areas)
                    min_power, max_power = min(pareto_powers), max(pareto_powers)
                    ax.axvspan(
                        max_area,
                        ax.get_xlim()[1],
                        alpha=0.1,
                        color="red",
                        label="Dominated Region",
                    )
                    ax.axhspan(max_power, ax.get_ylim()[1], alpha=0.1, color="red")

            # Add reference lines for best area and best power
            best_area_idx = all_areas.index(min(all_areas))
            best_power_idx = all_powers.index(min(all_powers))
            ax.axvline(
                all_areas[best_area_idx],
                color="blue",
                linestyle=":",
                alpha=0.5,
                linewidth=2,
                label="Best Area",
            )
            ax.axhline(
                all_powers[best_power_idx],
                color="green",
                linestyle=":",
                alpha=0.5,
                linewidth=2,
                label="Best Power",
            )

            ax.set_xlabel("Cell Area (um²)", fontsize=14, fontweight="bold")
            ax.set_ylabel("Power (uW)", fontsize=14, fontweight="bold")
            ax.set_title(
                "Area-Power Pareto Frontier\n(Lower-left is better)",
                fontsize=16,
                fontweight="bold",
                pad=15,
            )
            ax.legend(loc="upper right", fontsize=10, framealpha=0.95)
            ax.grid(True, alpha=0.3, linestyle="--")
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches="tight", dpi=300)
            plt.close()

        # Plot 4: Optimization History with improvement annotations
        fig, ax = plt.subplots(figsize=(11, 7))

        trial_numbers = [t["number"] for t in feasible]
        areas = [t["area"] for t in feasible]
        powers = [t["power"] for t in feasible]

        if trial_numbers:
            # Plot individual trials
            scatter = ax.scatter(
                trial_numbers,
                areas,
                c=powers,
                cmap="coolwarm",
                s=200,
                alpha=0.7,
                edgecolors="black",
                linewidth=1.5,
                label="Trial Results",
                zorder=3,
            )

            # Best so far curve
            best_so_far = []
            current_best = float("inf")
            improvement_trials = []
            for i, area in enumerate(areas):
                if area < current_best:
                    improvement_trials.append((trial_numbers[i], area))
                    current_best = area
                best_so_far.append(current_best)

            ax.plot(
                trial_numbers,
                best_so_far,
                "g-",
                linewidth=3.5,
                label="Best So Far",
                zorder=4,
                alpha=0.8,
            )

            # Mark improvements
            if improvement_trials:
                imp_nums, imp_areas = zip(*improvement_trials)
                ax.scatter(
                    imp_nums,
                    imp_areas,
                    c="gold",
                    s=400,
                    alpha=1.0,
                    edgecolors="black",
                    linewidth=2.5,
                    marker="D",
                    label="Improvement",
                    zorder=5,
                )

                # Annotate final best
                final_best_num, final_best_area = improvement_trials[-1]
                ax.annotate(
                    f"Final Best: {final_best_area:.3f} um²\n(Trial {final_best_num})",
                    xy=(final_best_num, final_best_area),
                    xytext=(20, 20),
                    textcoords="offset points",
                    bbox=dict(
                        boxstyle="round,pad=0.7", fc="gold", alpha=0.9, ec="black", lw=2
                    ),
                    arrowprops=dict(
                        arrowstyle="->", connectionstyle="arc3,rad=0.3", lw=2.5
                    ),
                    fontsize=10,
                    fontweight="bold",
                )

            # Colorbar for power
            cbar = plt.colorbar(scatter, ax=ax, pad=0.02)
            cbar.set_label("Power (uW)", fontsize=12, fontweight="bold")
            cbar.ax.tick_params(labelsize=10)

            # Add statistics text box
            if len(areas) > 1:
                stats_text = (
                    f"Total Trials: {len(trial_numbers)}\n"
                    f"Improvements: {len(improvement_trials)}\n"
                    f"Best Area: {min(areas):.3f} um²\n"
                    f"Worst Area: {max(areas):.3f} um²\n"
                    f"Range: {max(areas) - min(areas):.3f} um²"
                )
                ax.text(
                    0.02,
                    0.98,
                    stats_text,
                    transform=ax.transAxes,
                    fontsize=9,
                    verticalalignment="top",
                    bbox=dict(
                        boxstyle="round,pad=0.8",
                        fc="lightblue",
                        alpha=0.8,
                        ec="black",
                        lw=1.5,
                    ),
                )

        ax.set_xlabel("Trial Number", fontsize=14, fontweight="bold")
        ax.set_ylabel("Cell Area (um²)", fontsize=14, fontweight="bold")
        ax.set_title(
            "Optimization Convergence History", fontsize=16, fontweight="bold", pad=15
        )
        ax.legend(loc="upper right", fontsize=11, framealpha=0.9)
        ax.grid(True, alpha=0.3, linestyle="--")
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches="tight", dpi=300)
        plt.close()

        # Plot 5: 2D Parameter Space Exploration with annotations
        if len(feasible) > 3:
            fig, ax = plt.subplots(figsize=(12, 8))

            core_utils = [t["core_util"] for t in feasible]
            densities = [t["place_density"] for t in feasible]
            areas = [t["area"] for t in feasible]
            powers = [t["power"] for t in feasible]

            # Create scatter plot with area as color
            scatter = ax.scatter(
                core_utils,
                densities,
                c=areas,
                cmap="RdYlGn_r",
                s=400,
                alpha=0.85,
                edgecolors="black",
                linewidth=2,
                marker="o",
                zorder=3,
            )

            # Annotate each point with its area value
            for i, (cu, pd, area) in enumerate(zip(core_utils, densities, areas)):
                ax.annotate(
                    f"{area:.2f}",
                    xy=(cu, pd),
                    xytext=(0, 0),
                    textcoords="offset points",
                    fontsize=8,
                    fontweight="bold",
                    ha="center",
                    va="center",
                    color="white" if area > np.median(areas) else "black",
                )

            # Highlight best point
            best_idx = areas.index(min(areas))
            ax.scatter(
                [core_utils[best_idx]],
                [densities[best_idx]],
                s=700,
                facecolors="none",
                edgecolors="blue",
                linewidth=4,
                marker="o",
                label="Best Solution",
                zorder=5,
            )

            # Add infeasible points if any
            if infeasible:
                ax.scatter(
                    [t["core_util"] for t in infeasible],
                    [t["place_density"] for t in infeasible],
                    c="gray",
                    s=200,
                    alpha=0.4,
                    edgecolors="red",
                    linewidth=2,
                    marker="x",
                    label="Timing Violation",
                    zorder=2,
                )

            # Colorbar
            cbar = plt.colorbar(scatter, ax=ax, pad=0.02)
            cbar.set_label("Cell Area (um²)", fontsize=13, fontweight="bold")
            cbar.ax.tick_params(labelsize=10)

            # Add best point annotation box
            best_info = (
                f"Optimal Configuration:\n"
                f"CORE_UTIL = {core_utils[best_idx]}%\n"
                f"PLACE_DENSITY = {densities[best_idx]:.3f}\n"
                f"Area = {areas[best_idx]:.3f} um²\n"
                f"Power = {powers[best_idx]:.1f} uW"
            )
            ax.text(
                0.98,
                0.02,
                best_info,
                transform=ax.transAxes,
                fontsize=9,
                fontweight="bold",
                verticalalignment="bottom",
                horizontalalignment="right",
                bbox=dict(
                    boxstyle="round,pad=0.8",
                    fc="lightyellow",
                    alpha=0.95,
                    ec="blue",
                    lw=2.5,
                ),
            )

            # Add secondary scatter with power as size
            scatter2 = ax.scatter(
                core_utils,
                densities,
                s=[p * 15 for p in powers],
                facecolors="none",
                edgecolors="purple",
                linewidth=1.5,
                alpha=0.4,
                label="Size ∝ Power",
                zorder=2,
            )

            ax.set_xlabel("CORE_UTILIZATION (%)", fontsize=14, fontweight="bold")
            ax.set_ylabel("PLACE_DENSITY", fontsize=14, fontweight="bold")
            ax.set_title(
                "Design Space Exploration Map\n(Color = Area, Purple Circle Size ∝ Power)",
                fontsize=16,
                fontweight="bold",
                pad=15,
            )
            ax.legend(loc="upper left", fontsize=11, framealpha=0.95)
            ax.grid(True, alpha=0.3, linestyle="--")
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches="tight", dpi=300)
            plt.close()

    print(f"✓ Plots saved to {os.path.abspath(output_file)}")


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
