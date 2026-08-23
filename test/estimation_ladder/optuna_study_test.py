"""Machinery check for rung A of the estimation ladder study.

This test does not evaluate the study's conclusions -- it runs a handful
of trials on both designs and checks that the sweep produces a usable
archive, and that the ladder's basic premise still holds: the macro
design, whose near-critical paths are dominated by wires that do not
exist until placement, must be estimated *worse* by a synthesis-only
rung than the small wire-poor design is.

It runs the trials concurrently on purpose. Only the runtime axis is
sensitive to that, and this test does not look at runtime.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TRIALS = "8"
JOBS = "8"


def run_study(study_exe, estimator_exe, ground_truth, design_name, env):
    print(f"Running rung A for {design_name}...")
    res = subprocess.run(
        [
            study_exe,
            estimator_exe,
            ground_truth,
            design_name,
            "--trials",
            TRIALS,
            "--jobs",
            JOBS,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        sys.exit(f"rung A for {design_name} failed!\n{res.stdout}\n{res.stderr}")


def best_synth_only(archive):
    """Lowest mean relative error among trials that ran no placement."""
    errs = [
        row["metrics"]["mean_rel_err"]
        for row in archive
        if str(row["env"].get("RUN_PLACE", "0")) != "1"
    ]
    return min(errs) if errs else None


def main():
    if len(sys.argv) < 6:
        sys.exit(
            "Usage: optuna_study_test.py <optuna_study_exe> <estimator_exe> "
            "<ground_truth_json> <estimator_top_exe> <ground_truth_top_json>"
        )

    study_exe, estimator_exe, ground_truth, estimator_top_exe, ground_truth_top = (
        sys.argv[1:6]
    )

    temp_dir = tempfile.mkdtemp()
    try:
        env = os.environ.copy()
        env["BUILD_WORKSPACE_DIRECTORY"] = temp_dir
        out_dir = os.path.join(temp_dir, "test/estimation_ladder")
        os.makedirs(out_dir, exist_ok=True)

        run_study(study_exe, estimator_exe, ground_truth, "multiplier", env)
        run_study(study_exe, estimator_top_exe, ground_truth_top, "multiplier_top", env)

        archives = {}
        for design in ("multiplier", "multiplier_top"):
            path = os.path.join(out_dir, f"archive_{design}.json")
            with open(path) as f:
                archives[design] = json.load(f)
            if not archives[design]:
                sys.exit(f"FAIL: empty archive for {design}")
            required = {"mean_rel_err", "bias", "spread", "kendall_tau", "worst_recall"}
            missing = required - set(archives[design][0]["metrics"])
            if missing:
                sys.exit(f"FAIL: {design} archive is missing metrics {missing}")

        synth_simple = best_synth_only(archives["multiplier"])
        synth_top = best_synth_only(archives["multiplier_top"])
        if synth_simple is None or synth_top is None:
            sys.exit("FAIL: no synthesis-only trial in one of the archives")

        print(f"Best synth-only mean relative error (simple): {synth_simple}")
        print(f"Best synth-only mean relative error (top): {synth_top}")

        if synth_top <= synth_simple:
            sys.exit(
                "FAIL: expected the macro design to have WORSE synth-only "
                f"relative error ({synth_top}) than the simple design "
                f"({synth_simple})"
            )

        print("PASS: rung A produced usable archives for both designs.")
    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
