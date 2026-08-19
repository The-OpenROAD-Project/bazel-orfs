import sys
import os
import subprocess
import json
import optuna
import shutil
import pandas as pd
import scipy.stats
import tarfile

RUNFILES_DIR = os.environ.get("RUNFILES_DIR", os.getcwd())

def get_runfile(path):
    p = os.path.join(RUNFILES_DIR, "bazel-orfs", path)
    if os.path.exists(p): return os.path.abspath(p)
    p = os.path.join(RUNFILES_DIR, "_main", path)
    if os.path.exists(p): return os.path.abspath(p)
    p = os.path.join(RUNFILES_DIR, path)
    if os.path.exists(p): return os.path.abspath(p)
    return os.path.abspath(path)

def extract_deps():
    print("Extracting ORFS environment...")
    
    scratch_dir = "/tmp/orfs_optuna_scratch"
    if os.path.exists(scratch_dir):
        shutil.rmtree(scratch_dir)
    os.makedirs(scratch_dir, exist_ok=True)
    
    tar_path = get_runfile("test/estimation_ladder/multiplier_asap7_grt_deps_tar.tar.gz")
    
    print(f"Extracting {tar_path} to {scratch_dir}...")
    subprocess.run(["tar", "-xzf", tar_path, "-C", scratch_dir], check=True)
    subprocess.run(["chmod", "-R", "u+w", scratch_dir], check=True)
    
    make_dir = os.path.join(scratch_dir, "multiplier_asap7_grt_deps_run.sh.runfiles", "_main", "test", "estimation_ladder")
    return make_dir

def run_script(make_dir, script_path, db_path, sdc_path, out_json, env_vars=None):
    if env_vars is None: env_vars = {}
    
    cmd = [
        os.path.join(RUNFILES_DIR, "+orfs_repositories+gnumake", "make"),
        "-f", os.path.join(RUNFILES_DIR, "orfs+", "flow", "Makefile"),
        "DESIGN_CONFIG=" + get_runfile("test/estimation_ladder/results/asap7/multiplier/base/1_synth.short.mk"),
        "PLATFORM=asap7",
        "DESIGN_NAME=multiplier",
        f"PLATFORM_DIR={os.path.join(RUNFILES_DIR, 'orfs+', 'flow', 'platforms', 'asap7')}",
        f"OPENROAD_EXE={os.path.join(RUNFILES_DIR, 'openroad+', 'openroad')}",
        "run",
        f"RUN_SCRIPT={script_path}",
        f"ODB_FILE={db_path}",
        f"SDC_FILE={sdc_path}",
        f"OUTPUT_JSON={out_json}",
        f"RESULTS_DIR={os.path.dirname(db_path)}",
    ]
    
    print(f"Running: {' '.join(cmd)} in {make_dir}")
    
    env = os.environ.copy()
    for k, v in env_vars.items():
        if k == "SAMPLED_PATHS_JSON":
            cmd.insert(cmd.index("run") + 1, f"{k}={v}")
    
    if os.path.exists(out_json):
        os.remove(out_json)
        
    res = subprocess.run(cmd, cwd=make_dir, env=env, capture_output=True, text=True)
    if res.returncode != 0: print(f"OpenROAD error: {res.stderr}\nOpenROAD stdout: {res.stdout}")
    if not os.path.exists(out_json):
        print(f"FAILED TO PRODUCE {out_json}!! cmd: {' '.join(cmd)}\nstdout: {res.stdout}\nstderr: {res.stderr}")
    return res

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
    make_dir = extract_deps()
    
    # synth_db doesn't have floorplan set up which breaks OpenROAD placement logic, so use grt db
    fp_db = get_runfile("test/estimation_ladder/results/asap7/multiplier/base/5_1_grt.odb")
    synth_sdc = get_runfile("test/estimation_ladder/results/asap7/multiplier/base/1_synth.sdc")
    grt_db = get_runfile("test/estimation_ladder/results/asap7/multiplier/base/5_1_grt.odb")
    
    sampler_script = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".") + "/test/estimation_ladder/sampler.tcl"
    estimator_script = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".") + "/test/estimation_ladder/fast_estimator.tcl"
    
    # 1. Run Sampler on synth
    print("Sampling paths...")
    sampled_paths = os.path.abspath(os.path.join(make_dir, "sampled_paths.json"))
    run_script(make_dir, sampler_script, fp_db, synth_sdc, sampled_paths)
    print(f"What was OUT_JSON? {sampled_paths}")
    print(f"SAMPLED PATHS WAS PASSED TO RUN_SCRIPT AS: {sampled_paths}")
    print(f"Sampled paths created? {os.path.exists(sampled_paths)}")
    
    # 2. Extract Ground Truth from GRT
    print("Extracting Ground Truth...")
    run_script(make_dir, estimator_script, grt_db, synth_sdc, os.path.abspath(os.path.join(make_dir, "ground_truth.json")), env_vars={"RUN_PLACE": "0", "RUN_GRT": "0", "SAMPLED_PATHS_JSON": sampled_paths}) # wait, ground_truth needs sampled_paths! it should be from the sampler!
    
    def objective(trial):
        env = {
            "RUN_PLACE": str(trial.suggest_categorical("run_place", [0, 1]))
        }
        
        if env["RUN_PLACE"] == "1":
            env["PLACE_DENSITY"] = str(trial.suggest_float("place_density", 0.4, 0.9))
            env["PLACE_TIMING"] = str(trial.suggest_categorical("place_timing", [0, 1]))
            env["PLACE_ROUTABILITY"] = str(trial.suggest_categorical("place_routability", [0, 1]))
            env["RUN_GRT"] = str(trial.suggest_categorical("run_grt", [0, 1]))
            if env["RUN_GRT"] == "1":
    
                env["GRT_ITERATIONS"] = str(trial.suggest_int("grt_iterations", 0, 5))
        else:
            env["RUN_GRT"] = "0"
        env["SAMPLED_PATHS_JSON"] = sampled_paths
            
        out_json = os.path.abspath(os.path.join(make_dir, "est_results.json"))
        env["SAMPLED_PATHS_JSON"] = sampled_paths
        
        res = run_script(make_dir, estimator_script, fp_db, synth_sdc, out_json, env_vars=env)
        
        try:
            corr, rt = compute_correlation(os.path.abspath(os.path.join(make_dir, "ground_truth.json")), out_json)
        except Exception as e:
            # Bad execution
            print("Failed trial!")
            print(res.stderr)
            return 0.0, 999999
            
        # Maximize correlation, minimize runtime
        return corr, rt

    study = optuna.create_study(directions=["maximize", "minimize"])
    study.optimize(objective, n_trials=3, n_jobs=1)

    print("Study finished!")
    trials = study.best_trials
    
    data = []
    for t in trials:
        row = {"correlation": t.values[0], "runtime_ms": t.values[1]}
        row.update(t.params)
        data.append(row)
        
    df = pd.DataFrame(data)
    df = df.sort_values(by="correlation", ascending=False)
    print("\n--- PARETO FRONT ---")
    print(df.to_string(index=False))
    
    out_csv = "test/estimation_ladder/pareto_front.csv"
    
    # We must write to the actual source directory since bazel run is read-only
    src_dir = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    df.to_csv(os.path.join(src_dir, out_csv), index=False)
    print(f"\nSaved pareto front to {out_csv}")

if __name__ == "__main__":
    # Override get_runfile context inside the scratch dir
    RUNFILES_DIR = os.path.join("/tmp/orfs_optuna_scratch", "multiplier_asap7_grt_deps_run.sh.runfiles")
    main()
