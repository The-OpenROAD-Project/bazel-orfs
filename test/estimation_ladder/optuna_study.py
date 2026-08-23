import sys
import os
import subprocess
import json
import optuna
import tempfile
import pandas as pd


def compute_mean_rel_err(truth_json, est_json):
    with open(truth_json, "r") as f:
        truth = json.load(f)
    with open(est_json, "r") as f:
        est = json.load(f)

    truth_paths = {(p["start"], p["end"]): p["min_period"] for p in truth["paths"]}
    est_paths = {(p["start"], p["end"]): p["min_period"] for p in est["paths"]}
    if set(truth_paths) != set(est_paths):
        raise ValueError(
            "Estimator path set differs from ground truth: "
            f"missing {set(truth_paths) - set(est_paths)}, "
            f"extra {set(est_paths) - set(truth_paths)}"
        )

    mean_rel_err = sum(
        abs(est_paths[k] - truth_paths[k]) / truth_paths[k] for k in truth_paths
    ) / len(truth_paths)
    runtime = est["runtime_s"]

    return mean_rel_err, runtime


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
        run_place = trial.suggest_categorical("run_place", [0, 1])
        env = {
            "RUN_PLACE": str(run_place),
            "GPL_TIMING_DRIVEN": "0",
            "GPL_ROUTABILITY_DRIVEN": "0",
            "RUN_GRT": "0",
            "GRT_ITERATIONS": "0",
            "GROUND_TRUTH_JSON": ground_truth_json,
        }

        # The ladder is synth -> +place -> +grt: only suggest parameters
        # for rungs that actually run, so Pareto front rows don't report
        # knobs that had no effect.
        if run_place == 1:
            env["GPL_TIMING_DRIVEN"] = str(
                trial.suggest_categorical("place_timing", [0, 1])
            )
            env["GPL_ROUTABILITY_DRIVEN"] = str(
                trial.suggest_categorical("place_routability", [0, 1])
            )
            env["RUN_GRT"] = str(trial.suggest_categorical("run_grt", [0, 1]))

        if env["RUN_GRT"] == "1":
            env["GRT_ITERATIONS"] = str(trial.suggest_int("grt_iterations", 1, 5))

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
                raise optuna.TrialPruned()

            rel_err, rt = compute_mean_rel_err(ground_truth_json, out_json)
        finally:
            if os.path.exists(out_json):
                os.remove(out_json)

        return rel_err, rt

    study = optuna.create_study(directions=["minimize", "minimize"])
    study.optimize(objective, n_trials=15, n_jobs=8)

    print("Study finished!")
    trials = study.best_trials

    if not trials:
        print("No valid trials found!")
        df = pd.DataFrame(
            columns=[
                "mean_rel_err",
                "runtime_s",
                "run_place",
                "place_timing",
                "place_routability",
                "run_grt",
            ]
        )
    else:
        data = []
        for t in trials:
            row = {"mean_rel_err": t.values[0], "runtime_s": t.values[1]}
            row.update(t.params)
            data.append(row)

        df = pd.DataFrame(data)
        # Repeated trials with identical parameters land on the Pareto
        # front as identical rows; they carry no information.
        df = df.drop_duplicates()
        df = df.sort_values(by="mean_rel_err", ascending=True)

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
