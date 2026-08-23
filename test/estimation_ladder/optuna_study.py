import sys
import os
import subprocess
import json
import optuna
import tempfile
import pandas as pd
import scipy.stats


def compute_correlation(truth_json, est_json):
    with open(truth_json, "r") as f:
        truth = json.load(f)
    with open(est_json, "r") as f:
        est = json.load(f)

    truth_slacks = [p["min_period"] for p in truth["paths"]]
    est_slacks = [p["min_period"] for p in est["paths"]]

    corr, _ = scipy.stats.pearsonr(truth_slacks, est_slacks)
    runtime = est["runtime_ms"]

    return corr, runtime


def main():
    print("Starting Optuna Campaign for Fast Estimator...")

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: optuna_study.py <estimator_exe> <ground_truth_json> <design_name>"
        )

    estimator_exe = sys.argv[1]
    ground_truth_json = sys.argv[2]
    design_name = sys.argv[3]

    if not os.path.exists(estimator_exe):
        sys.exit(f"Estimator executable not found at {estimator_exe}")
    if not os.path.exists(ground_truth_json):
        sys.exit(f"Ground truth JSON not found at {ground_truth_json}")

    def objective(trial):
        env = {
            "RUN_PLACE": str(trial.suggest_categorical("run_place", [0, 1])),
            "GPL_TIMING_DRIVEN": str(trial.suggest_categorical("place_timing", [0, 1])),
            "GPL_ROUTABILITY_DRIVEN": str(
                trial.suggest_categorical("place_routability", [0, 1])
            ),
            "RUN_GRT": str(trial.suggest_categorical("run_grt", [0, 1])),
            "GROUND_TRUTH_JSON": ground_truth_json,
        }

        if env["RUN_GRT"] == "1":
            env["GRT_ITERATIONS"] = str(trial.suggest_int("grt_iterations", 1, 5))
        else:
            env["GRT_ITERATIONS"] = "0"

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            out_json = tf.name

        env["OUTPUT_JSON"] = out_json

        cmd = [estimator_exe]
        for k, v in env.items():
            cmd.append(f"{k}={v}")

        try:
            full_env = os.environ.copy()
            full_env.update(env)

            res = subprocess.run(
                cmd,
                env=full_env,
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                print(
                    f"Estimator failed (code {res.returncode}):\nstdout: {res.stdout}\nstderr: {res.stderr}"
                )
                return 0.0, 999999

            corr, rt = compute_correlation(ground_truth_json, out_json)
        finally:
            if os.path.exists(out_json):
                os.remove(out_json)

        return corr, rt

    study = optuna.create_study(directions=["maximize", "minimize"])
    n_jobs = 8 if "TEST_TMPDIR" in os.environ or "TEST_WORKSPACE" in os.environ else 1
    study.optimize(objective, n_trials=15, n_jobs=n_jobs)

    print("Study finished!")
    trials = [t for t in study.best_trials if t.values[0] > 0]

    if not trials:
        print("No valid trials found!")
        df = pd.DataFrame(
            columns=[
                "correlation",
                "runtime_ms",
                "run_place",
                "place_timing",
                "place_routability",
                "run_grt",
            ]
        )
    else:
        data = []
        for t in trials:
            row = {"correlation": t.values[0], "runtime_ms": t.values[1]}
            row.update(t.params)
            data.append(row)

        df = pd.DataFrame(data)
        df = df.sort_values(by="correlation", ascending=False)

    print("\n--- PARETO FRONT ---")
    print(df.to_string(index=False))

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.environ.get("PWD", ".")
    out_path = os.path.join(
        ws, f"test/estimation_ladder/pareto_front_{design_name}.csv"
    )
    df.to_csv(out_path, index=False)
    print(f"\nSaved pareto front to {out_path}")


if __name__ == "__main__":
    main()
