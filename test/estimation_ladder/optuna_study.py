"""Rung A of the estimation ladder study: the correlation sweep.

This rung searches the estimator's knob space for accuracy alone and
deliberately does *not* optimize runtime.  It runs many estimators
concurrently, so every wall-clock number it observes is contaminated by
contention between them -- a configuration is not slow because of its
knobs, it is slow because seven siblings were competing for the machine.
Accuracy has no such problem: it is a property of the placement and the
parasitics, not of the scheduler.

Runtime is measured separately, one process at a time, by
measure_runtime.py (rung B), which picks the configurations to time out
of the archive this rung writes.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile

import optuna

from estimation_metrics import compute_metrics


def build_env(trial):
    """Sample one estimator configuration.

    Knobs are only sampled for rungs that actually run, so an archive row
    never reports a setting that had no effect on the result.
    """
    env = {}

    run_place = trial.suggest_categorical("run_place", [0, 1])
    env["RUN_PLACE"] = str(run_place)
    env["RUN_MACRO_PLACE"] = str(trial.suggest_categorical("run_macro_place", [0, 1]))

    # Which routing layer prices a wire. Free at runtime, and measured
    # separately as the most effective single knob in the study -- it is
    # in the search space now because leaving it out is what made an
    # earlier sweep conclude that nothing could fix macro path ordering.
    wire_rc = trial.suggest_categorical(
        "wire_rc_layer",
        ["default", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9"],
    )
    if wire_rc != "default":
        env["WIRE_RC_LAYER_OVERRIDE"] = wire_rc

    gp_args = []
    if run_place == 1:
        # -place_ios is a branch rather than another dimension: gpl
        # refuses it alongside -timing_driven and -routability_driven, so
        # sampling them independently would waste trials on combinations
        # the tool rejects outright.
        place_ios = trial.suggest_categorical("place_ios", [0, 1])
        env["PLACE_IOS"] = str(place_ios)
        if place_ios == 0:
            env["GPL_TIMING_DRIVEN"] = str(
                trial.suggest_categorical("place_timing", [0, 1])
            )
            env["GPL_ROUTABILITY_DRIVEN"] = str(
                trial.suggest_categorical("place_routability", [0, 1])
            )
            if env["GPL_ROUTABILITY_DRIVEN"] == "1":
                gp_args += [
                    "-routability_check_overflow",
                    str(trial.suggest_float("routability_check_overflow", 0.2, 0.5)),
                ]
                if trial.suggest_categorical("routability_use_grt", [0, 1]):
                    gp_args.append("-routability_use_grt")

        # The Nesterov termination threshold: the single largest runtime
        # dial in gpl, and the one most likely to trade accuracy for it.
        gp_args += ["-overflow", str(trial.suggest_float("overflow", 0.05, 0.40))]
        gp_args += [
            "-initial_place_max_iter",
            str(trial.suggest_int("initial_place_max_iter", 0, 20)),
        ]
        gp_args += [
            "-initial_place_max_fanout",
            str(trial.suggest_int("initial_place_max_fanout", 50, 400)),
        ]
        gp_args += [
            "-init_wirelength_coef",
            str(trial.suggest_float("init_wirelength_coef", 0.05, 1.0)),
        ]
        bin_grid = trial.suggest_categorical("bin_grid_count", [0, 64, 128, 256])
        if bin_grid:
            gp_args += ["-bin_grid_count", str(bin_grid)]

        min_phi = trial.suggest_float("min_phi_coef", 0.85, 1.0)
        max_phi = trial.suggest_float("max_phi_coef", 1.0, 1.15)
        gp_args += ["-min_phi_coef", str(min_phi), "-max_phi_coef", str(max_phi)]

        # The virtual clock tree lives inside global placement, so it is
        # only reachable on this branch.
        env["GPL_VIRTUAL_CTS"] = str(trial.suggest_categorical("virtual_cts", [0, 1]))

        clock_mode = trial.suggest_categorical(
            "clock_mode", ["none", "propagated", "real"]
        )
        env["CLOCK_MODE"] = clock_mode
        if clock_mode == "real":
            env["CTS_DPL"] = str(trial.suggest_categorical("cts_dpl", [0, 1]))

        if trial.suggest_categorical("repair_design", [0, 1]):
            env["RUN_REPAIR_DESIGN"] = "1"
            # No -pre_placement here: it is gain-based buffering for the
            # post-synthesis state, before a placement exists, and ORFS
            # only ever calls it that way. Against a placed design with
            # placement parasitics it trips EST-0104, so sampling it
            # would only burn trials on a configuration OpenROAD
            # refuses to run.
            rd = []
            rd += ["-slew_margin", str(trial.suggest_float("slew_margin", 0.0, 20.0))]
            rd += ["-cap_margin", str(trial.suggest_float("cap_margin", 0.0, 20.0))]
            env["REPAIR_DESIGN_ARGS"] = " ".join(rd)

        run_grt = trial.suggest_categorical("run_grt", [0, 1])
        env["RUN_GRT"] = str(run_grt)
        if run_grt == 1:
            env["GRT_ITERATIONS"] = str(trial.suggest_int("grt_iterations", 1, 30))
            grt = []
            if trial.suggest_categorical("grt_use_cugr", [0, 1]):
                grt.append("-use_cugr")
            if trial.suggest_categorical("grt_allow_congestion", [0, 1]):
                grt.append("-allow_congestion")
            grt += [
                "-critical_nets_percentage",
                str(trial.suggest_float("critical_nets_percentage", 0.0, 30.0)),
            ]
            env["GRT_ARGS"] = " ".join(grt)

        # repair_timing is only meaningful once there are parasitics to
        # repair against, and -hold is excluded on purpose: the metric is
        # the minimum clock period, so hold repair can only cost runtime.
        if trial.suggest_categorical("repair_timing", [0, 1]):
            env["RUN_REPAIR_TIMING"] = "1"
            # Braced: the estimator evals this string as Tcl, so a
            # multi-word sequence would otherwise arrive as trailing
            # positional arguments and repair_timing rejects those
            # (STA-0564).
            sequence = trial.suggest_categorical(
                "repair_timing_sequence",
                ["vt_swap", "vt_swap reroute", "buffer vt_swap reroute"],
            )
            rt = [
                "-sequence",
                "{" + sequence + "}",
                "-repair_tns",
                str(trial.suggest_categorical("repair_tns", [0, 50, 100])),
                "-max_passes",
                str(trial.suggest_int("repair_max_passes", 1, 10)),
            ]
            if trial.suggest_categorical("repair_skip_last_gasp", [0, 1]):
                rt.append("-skip_last_gasp")
            if trial.suggest_categorical("repair_skip_gate_cloning", [0, 1]):
                rt.append("-skip_gate_cloning")
            env["REPAIR_TIMING_ARGS"] = " ".join(rt)

    if gp_args:
        env["GP_ARGS"] = " ".join(gp_args)
    return env


def run_estimator(estimator_exe, env, ground_truth_json, timeout_s=None, out_json=None):
    """Run one estimator configuration and return its metrics.

    A timeout is not a nicety for an unattended sweep: the knob space
    contains configurations -- thirty congestion iterations alongside a
    full repair_timing sequence -- that can run far longer than any rung
    worth putting on a Pareto front, and one of them would otherwise
    stall the study for hours.
    """
    env = dict(env)
    env["GROUND_TRUTH_JSON"] = ground_truth_json

    # Callers that want the per-path output kept -- the calibration
    # transfer needs the periods themselves, not just the summary --
    # pass a path; the sweep does not, and gets a scratch file.
    keep = out_json is not None
    if not keep:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            out_json = tf.name
    env["OUTPUT_JSON"] = out_json

    cmd = [estimator_exe] + [f"{k}={v}" for k, v in env.items()]
    try:
        full_env = os.environ.copy()
        full_env.update(env)
        try:
            res = subprocess.run(
                cmd,
                env=full_env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"estimator exceeded {timeout_s}s; treating as unusable")
        if res.returncode != 0:
            raise RuntimeError(
                f"estimator exited {res.returncode}\n"
                f"stdout: {res.stdout[-4000:]}\nstderr: {res.stderr[-4000:]}"
            )
        metrics, _ = compute_metrics(ground_truth_json, out_json)
    finally:
        if not keep and os.path.exists(out_json):
            os.remove(out_json)
    return metrics


def run_estimator_batch(
    estimator_exe,
    envs_by_id,
    ground_truth_json,
    timeout_s=None,
    parallel=False,
    subtree_timeout_s=None,
    keep_results_dir=None,
):
    """Run many configurations in ONE estimator process.

    The estimator walks the configurations as a decision tree, forking at
    each divergence (see estimator_batch.tcl), so a stage shared by two
    trials -- most importantly the design load and floorplan every trial
    shares -- is paid once instead of once per trial.

    The walk is sequential by default (one active run owns the machine,
    the honest setting for anything that reads runtimes); parallel=True
    forks divergent subtrees concurrently, which restores the old
    jobs-style concurrency for accuracy-only callers.

    Returns {id: metrics or None}: an id whose subtree crashed has no leaf
    JSON and maps to None, while its siblings still report.
    """
    work = tempfile.mkdtemp(prefix="est_batch_")
    manifest_dir = os.path.join(work, "manifest")
    results_dir = os.path.join(work, "results")
    os.makedirs(manifest_dir)
    os.makedirs(results_dir)
    ground_truth = os.path.abspath(ground_truth_json)
    try:
        for cid, env in envs_by_id.items():
            with open(os.path.join(manifest_dir, f"{cid}.cfg"), "w") as f:
                for key, value in env.items():
                    f.write(f"{key}={value}\n")

        cmd = [
            estimator_exe,
            f"EST_MANIFEST_DIR={manifest_dir}",
            f"EST_RESULTS_DIR={results_dir}",
            f"GROUND_TRUTH_JSON={ground_truth}",
            f"LOG_DIR={work}",
        ]
        if parallel:
            cmd.append("EST_PARALLEL=1")
            # Every forked child inherits the tool's thread count; a wave
            # of concurrent subtrees each sized for the whole machine is
            # oversubscription, not speed. Divide the machine instead.
            threads = max(1, (os.cpu_count() or 8) // max(1, len(envs_by_id)))
            cmd.append(f"NUM_CORES={threads}")
        if subtree_timeout_s is not None:
            # The batch-level timeout below is a backstop; this is the
            # per-trial budget, enforced inside the walk (a runaway
            # subtree is killed, its siblings still report).
            cmd.append(f"EST_SUBTREE_TIMEOUT={subtree_timeout_s}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"estimator batch exceeded {timeout_s}s")
        if res.returncode != 0:
            raise RuntimeError(
                f"estimator batch exited {res.returncode}\n"
                f"stdout: {res.stdout[-4000:]}\nstderr: {res.stderr[-4000:]}"
            )

        results = {}
        for cid in envs_by_id:
            leaf = os.path.join(results_dir, f"{cid}.json")
            if os.path.exists(leaf):
                metrics, _ = compute_metrics(ground_truth, leaf)
                results[cid] = metrics
            else:
                results[cid] = None
        if keep_results_dir:
            # Preserve the wave's leaf JSONs and edges.jsonl (the per-edge
            # instrumentation wave_savings.py aggregates).
            shutil.copytree(results_dir, keep_results_dir)
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)


def objective_values(metrics, subset):
    """The study's two objectives, or ValueError if the subset is empty.

    Maximizing rank correlation and minimizing the *magnitude* of the
    bias: a large bias that is consistent is a calibration constant, so
    it should not be penalized by its sign.
    """
    suffix = "" if subset == "all" else f"_{subset}"
    tau = metrics.get(f"kendall_tau{suffix}")
    bias = metrics.get(f"bias{suffix}")
    if tau is None or bias is None or tau != tau:
        raise ValueError(f"no {subset} metrics for this trial")
    return tau, abs(bias)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("estimator_exe")
    ap.add_argument("ground_truth_json")
    ap.add_argument("design_name")
    ap.add_argument("--trials", type=int, default=400)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument(
        "--subset",
        choices=["all", "macro", "nonmacro"],
        default="all",
        help=(
            "which population to optimize for. On a macro design the macro "
            "paths are a separate population with their own error structure "
            "-- faster, never near-critical, and ordered far worse -- so a "
            "sweep guided by the combined average optimizes for the non-macro "
            "majority and never explores what the macro paths need."
        ),
    )
    ap.add_argument(
        "--trial-timeout",
        type=float,
        default=1800.0,
        help="seconds before a single estimator run is abandoned",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help=(
            "run trials in fork/join batches of this size: one estimator "
            "process walks each batch as a decision tree, paying shared "
            "stages (load, floorplan, common placements) once instead of "
            "once per trial. 0 keeps the one-process-per-trial behavior. "
            "--jobs applies only to that legacy mode; the batch walk is "
            "sequential by default, one active run at a time. The batch "
            "timeout is --trial-timeout times the batch size."
        ),
    )
    ap.add_argument(
        "--keep-waves",
        default="",
        metavar="DIR",
        help=(
            "preserve each batch wave's results folder (leaf JSONs plus "
            "edges.jsonl) under DIR/wave_NNN, for wave_savings.py to "
            "estimate what a resident-root or snapshot-cache mode would "
            "have saved across the study"
        ),
    )
    ap.add_argument(
        "--batch-parallel",
        action="store_true",
        help=(
            "fork divergent subtrees of a batch concurrently instead of "
            "sequentially. Runtime numbers become contention-contaminated, "
            "so this is for accuracy-only sweeps (this rung's purpose) and "
            "the machinery test; leave it off when runtimes matter."
        ),
    )
    args = ap.parse_args()

    for path in (args.estimator_exe, args.ground_truth_json):
        if not os.path.exists(path):
            raise SystemExit(f"not found: {path}")

    archive = []

    def record(trial, env, metrics):
        trial.set_user_attr("env", env)
        for key, value in metrics.items():
            if key != "phases":
                trial.set_user_attr(key, value)
        archive.append({"number": trial.number, "env": env, "metrics": metrics})

    def objective(trial):
        env = build_env(trial)
        metrics = run_estimator(
            args.estimator_exe,
            env,
            args.ground_truth_json,
            timeout_s=args.trial_timeout,
        )
        record(trial, env, metrics)
        return objective_values(metrics, args.subset)

    study = optuna.create_study(
        directions=["maximize", "minimize"],
        sampler=optuna.samplers.NSGAIISampler(seed=1),
    )
    if args.batch_size > 0:
        done = 0
        wave_number = 0
        while done < args.trials:
            wave = min(args.batch_size, args.trials - done)
            trials = [study.ask() for _ in range(wave)]
            envs = {str(t.number): build_env(t) for t in trials}
            keep = None
            if args.keep_waves:
                keep = os.path.join(args.keep_waves, f"wave_{wave_number:03d}")
            batch = run_estimator_batch(
                args.estimator_exe,
                envs,
                args.ground_truth_json,
                timeout_s=args.trial_timeout * wave,
                parallel=args.batch_parallel,
                subtree_timeout_s=args.trial_timeout,
                keep_results_dir=keep,
            )
            wave_number += 1
            for t in trials:
                metrics = batch.get(str(t.number))
                try:
                    if metrics is None:
                        raise RuntimeError("subtree crashed; no leaf JSON")
                    values = objective_values(metrics, args.subset)
                except (RuntimeError, ValueError) as e:
                    print(f"trial {t.number} failed: {e}")
                    study.tell(t, state=optuna.trial.TrialState.FAIL)
                    continue
                record(t, envs[str(t.number)], metrics)
                study.tell(t, values)
            done += wave
    else:
        study.optimize(
            objective,
            n_trials=args.trials,
            n_jobs=args.jobs,
            catch=(RuntimeError, ValueError, TimeoutError),
        )

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.environ.get("PWD", ".")
    out_dir = os.path.join(ws, "test/estimation_ladder")
    archive_path = os.path.join(out_dir, f"archive_{args.design_name}.json")
    with open(archive_path, "w") as f:
        json.dump(archive, f, indent=2, sort_keys=True)
    print(f"Wrote {len(archive)} trials to {archive_path}")


if __name__ == "__main__":
    main()
