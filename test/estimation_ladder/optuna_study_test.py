import sys
import os
import subprocess
import pandas as pd
import tempfile
import shutil


def run_study(study_exe, estimator_exe, ground_truth, design_name, env):
    print(f"Running optuna_study for {design_name}...")
    res = subprocess.run(
        [study_exe, estimator_exe, ground_truth, design_name],
        env=env,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        sys.exit(f"optuna_study for {design_name} failed!\n{res.stdout}\n{res.stderr}")


def main():
    if len(sys.argv) < 6:
        sys.exit(
            "Usage: optuna_study_test.py <optuna_study_exe> <estimator_exe> <ground_truth_json> <estimator_top_exe> <ground_truth_top_json>"
        )

    study_exe = sys.argv[1]
    estimator_exe = sys.argv[2]
    ground_truth = sys.argv[3]
    estimator_top_exe = sys.argv[4]
    ground_truth_top = sys.argv[5]

    # We will run optuna_study using subprocess and check its output pareto front
    temp_dir = tempfile.mkdtemp()
    try:
        env = os.environ.copy()
        env["BUILD_WORKSPACE_DIRECTORY"] = temp_dir

        # Creating a dummy test/estimation_ladder directory in the temp dir so study can save the csv
        os.makedirs(os.path.join(temp_dir, "test/estimation_ladder"), exist_ok=True)

        run_study(study_exe, estimator_exe, ground_truth, "multiplier", env)
        run_study(study_exe, estimator_top_exe, ground_truth_top, "multiplier_top", env)

        df_simple = pd.read_csv(
            os.path.join(temp_dir, "test/estimation_ladder/pareto_front_multiplier.csv")
        )
        df_top = pd.read_csv(
            os.path.join(
                temp_dir, "test/estimation_ladder/pareto_front_multiplier_top.csv"
            )
        )

        synth_only_simple = df_simple[df_simple["run_place"] == 0]["mean_rel_err"]
        synth_only_top = df_top[df_top["run_place"] == 0]["mean_rel_err"]
        if synth_only_simple.empty or synth_only_top.empty:
            sys.exit("FAIL: No synth-only (run_place=0) trial on a Pareto front")

        synth_simple = synth_only_simple.min()
        synth_top = synth_only_top.min()

        print(f"Best synth-only mean relative error (simple): {synth_simple}")
        print(f"Best synth-only mean relative error (top): {synth_top}")

        if synth_top <= synth_simple:
            sys.exit(
                f"FAIL: Expected complex top design to have WORSE synth-only relative error ({synth_top}) than simple design ({synth_simple})"
            )

        print("PASS: Estimation ladder evaluated for both designs.")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
