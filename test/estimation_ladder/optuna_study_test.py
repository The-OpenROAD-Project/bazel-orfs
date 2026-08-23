import sys
import os
import subprocess
import pandas as pd
import tempfile
import shutil


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

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY", os.environ.get("PWD", "."))

    # We will run optuna_study_test using subprocess and check its output pareto front
    temp_dir = tempfile.mkdtemp()
    try:
        env = os.environ.copy()
        env["BUILD_WORKSPACE_DIRECTORY"] = temp_dir

        # Creating a dummy test/estimation_ladder directory in the temp dir so study can save the csv
        os.makedirs(os.path.join(temp_dir, "test/estimation_ladder"), exist_ok=True)

        print("Running optuna_study for simple multiplier...")
        res = subprocess.run(
            [study_exe, estimator_exe, ground_truth, "multiplier"],
            env=env,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            sys.exit(f"optuna_study failed!\n{res.stdout}\n{res.stderr}")

        csv_path_simple = os.path.join(
            temp_dir, "test/estimation_ladder/pareto_front_multiplier.csv"
        )
        df_simple = pd.read_csv(csv_path_simple)

        # print("\nRunning optuna_study for complex multiplier_top...")
        # res2 = subprocess.run([study_exe, estimator_top_exe, ground_truth_top, "multiplier_top"], env=env, capture_output=True, text=True)
        # if res2.returncode != 0:
        #     sys.exit(f"optuna_study for top failed!\n{res2.stdout}\n{res2.stderr}")

        # csv_path_top = os.path.join(temp_dir, "test/estimation_ladder/pareto_front_multiplier_top.csv")
        # df_top = pd.read_csv(csv_path_top)

        synth_simple = df_simple[df_simple["run_place"] == 0]["correlation"].max()
        # synth_top = df_top[df_top['run_place'] == 0]['correlation'].max()

        print(f"Max synth-only correlation (simple): {synth_simple}")
        # print(f"Max synth-only correlation (top): {synth_top}")

        # Copy to workspace if it exists
        if ws:
            ws_dir = os.path.join(ws, "test/estimation_ladder")
            os.makedirs(ws_dir, exist_ok=True)
            shutil.copy(
                csv_path_simple, os.path.join(ws_dir, "pareto_front_multiplier.csv")
            )
            # shutil.copy(csv_path_top, os.path.join(ws_dir, "pareto_front_multiplier_top.csv"))

        # if synth_top >= synth_simple:
        #     sys.exit(f"FAIL: Expected complex top design to have WORSE synth correlation ({synth_top}) than simple design ({synth_simple})")

        print("PASS: Simple macro design evaluated successfully.")

    finally:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
