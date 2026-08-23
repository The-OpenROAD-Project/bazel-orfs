import sys
import os
import subprocess
import json
import optuna
import tempfile
import pandas as pd
import scipy.stats

RUNFILES_DIR = os.environ.get("RUNFILES_DIR", os.getcwd())

def get_runfile(path):
    p = os.path.join(RUNFILES_DIR, "bazel-orfs", path)
    if os.path.exists(p): return os.path.abspath(p)
    p = os.path.join(RUNFILES_DIR, "_main", path)
    if os.path.exists(p): return os.path.abspath(p)
    p = os.path.join(RUNFILES_DIR, path)
    if os.path.exists(p): return os.path.abspath(p)
    return os.path.abspath(path)

def compute_correlation(truth_json, est_json):
    with open(truth_json, 'r') as f: truth = json.load(f)
    with open(est_json, 'r') as f: est = json.load(f)
    
    truth_slacks = [p['slack'] for p in truth['paths']]
    est_slacks = [p['slack'] for p in est['paths']]
    
    corr, _ = scipy.stats.pearsonr(truth_slacks, est_slacks)
    runtime = est.get('runtime_ms', 999999)
    
    return corr, runtime

def main():
    print("Starting Optuna Campaign for Fast Estimator...")
    
    estimator_exe = get_runfile("test/estimation_ladder/run_fast_estimator_executable_base_executable")
    ground_truth_json = get_runfile("test/estimation_ladder/ground_truth.json")
    
    if not os.path.exists(estimator_exe):
        sys.exit(f"Estimator executable not found at {estimator_exe}")
    if not os.path.exists(ground_truth_json):
        sys.exit(f"Ground truth JSON not found at {ground_truth_json}")
        
    def objective(trial):
        env = {
            "RUN_PLACE": "1",
            "PLACE_DENSITY": "0.65",
            "PLACE_TIMING": str(trial.suggest_categorical("place_timing", [0, 1])),
            "PLACE_ROUTABILITY": str(trial.suggest_categorical("place_routability", [0, 1])),
            "RUN_GRT": str(trial.suggest_categorical("run_grt", [0, 1])),
            "GROUND_TRUTH_JSON": ground_truth_json,
        }
        
        if env["RUN_GRT"] == "1":
            env["GRT_ITERATIONS"] = str(trial.suggest_int("grt_iterations", 0, 5))
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
                print(f"Estimator failed (code {res.returncode}):\nstdout: {res.stdout}\nstderr: {res.stderr}")
                return 0.0, 999999
                
            corr, rt = compute_correlation(ground_truth_json, out_json)
        except Exception as e:
            print(f"Failed trial: {e}")
            return 0.0, 999999
        finally:
            if os.path.exists(out_json):
                os.remove(out_json)
                
        return corr, rt

    study = optuna.create_study(directions=["maximize", "minimize"])
    study.optimize(objective, n_trials=15, n_jobs=1)

    print("Study finished!")
    trials = [t for t in study.best_trials if t.values[0] > 0]
    
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
    out_path = os.path.join(ws, "test/estimation_ladder/pareto_front.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved pareto front to {out_path}")

if __name__ == "__main__":
    main()
