"""Machinery of rung A's fork/join batch walk, with no OpenROAD in sight.

//test/estimation_ladder:optuna_study_test is the full dress rehearsal: it
runs the real estimator over the real ground truth, and its ground_truth.json
is an ORFS flow output, so building it means running the multiplier design to
grt. That is minutes-to-hours work and it stays manual.

What CI needs to catch is different and cheaper: the plumbing around the
estimator. The study drives the estimator as an *external executable* -- a
manifest of `<id>.cfg` files in, a leaf JSON per id out, `leaf <id> done` on
stdout -- so a fake estimator exercises the whole walk in milliseconds: waves
are cut to --batch-size, one process serves a whole wave, a subtree that
produces no leaf is failed rather than crashing the study, --batch-parallel
reaches the walk, and the legacy one-process-per-trial mode still honours its
timeout.

Deliberately absent: any assertion about accuracy. A fake estimator's numbers
are made up, so a claim about mean_rel_err or path ordering proved here would
be a claim about this file. The estimator's fidelity is the real test's
business; this one only proves the machinery around it works.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

import optuna

import optuna_study

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Enough paths for worst_recall's k=10 and for _subset_metrics to emit both
# populations (it needs two of each).
GROUND_TRUTH = {
    "time_unit": "ps",
    "paths": [
        {
            "start": f"reg{i}/CK",
            "end": f"reg{i + 1}/D",
            "min_period": 100.0 + 7 * i,
            "macro_path": i % 4 == 0,
        }
        for i in range(12)
    ],
}

# A fake estimator: reads the manifest (or OUTPUT_JSON in legacy mode),
# writes a leaf per configuration whose periods are the ground truth scaled
# by a factor derived from the config, and appends what it was asked to do to
# calls.jsonl so the test can assert on the protocol rather than on numbers.
FAKE_ESTIMATOR = '''
import json
import os
import sys
import time

args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
calls = os.environ["FAKE_CALLS"]
crash = set(filter(None, os.environ.get("FAKE_CRASH_IDS", "").split(",")))
stall_s = float(os.environ.get("FAKE_STALL_S", "0"))

truth = json.load(open(args["GROUND_TRUTH_JSON"]))


def leaf(cfg_text):
    """Ground truth with every period nudged, deterministically per config."""
    factor = 1.0 + (len(cfg_text) % 17) / 100.0
    return {
        "time_unit": truth["time_unit"],
        "runtime_s": 0.1,
        "phases": {"load": 0.05},
        "paths": [dict(p, min_period=p["min_period"] * factor) for p in truth["paths"]],
    }


record = {"argv": sys.argv[1:], "env_parallel": os.environ.get("EST_PARALLEL")}

if "EST_MANIFEST_DIR" in args:
    manifest = args["EST_MANIFEST_DIR"]
    results = args["EST_RESULTS_DIR"]
    cfgs = {}
    for name in sorted(os.listdir(manifest)):
        cid = name[: -len(".cfg")]
        cfgs[cid] = open(os.path.join(manifest, name)).read()
    record["cfgs"] = cfgs
    record["mode"] = "batch"
    with open(calls, "a") as f:
        f.write(json.dumps(record) + "\\n")
    if stall_s:
        time.sleep(stall_s)
    for cid, text in cfgs.items():
        if cid in crash:
            print(f"subtree {cid} failed")
            continue
        with open(os.path.join(results, cid + ".json"), "w") as f:
            json.dump(leaf(text), f)
        print(f"leaf {cid} done")
else:
    record["mode"] = "single"
    record["cfgs"] = {"-": json.dumps(args, sort_keys=True)}
    with open(calls, "a") as f:
        f.write(json.dumps(record) + "\\n")
    if stall_s:
        time.sleep(stall_s)
    with open(args["OUTPUT_JSON"], "w") as f:
        json.dump(leaf(json.dumps(args, sort_keys=True)), f)
'''


class StudyMachineryTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="study_machinery_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.out_dir = os.path.join(self.root, "test/estimation_ladder")
        os.makedirs(self.out_dir)

        self.truth = os.path.join(self.root, "ground_truth.json")
        with open(self.truth, "w") as f:
            json.dump(GROUND_TRUTH, f)

        script = os.path.join(self.root, "fake_estimator.py")
        with open(script, "w") as f:
            f.write(FAKE_ESTIMATOR)
        # A shell wrapper around this interpreter, not a `#!` line: the study
        # execs the estimator directly, and the hermetic python is the one
        # running these tests, not whatever `python3` the host may have.
        self.exe = os.path.join(self.root, "fake_estimator")
        with open(self.exe, "w") as f:
            f.write(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        os.chmod(self.exe, 0o755)

        self.calls_path = os.path.join(self.root, "calls.jsonl")

    def run_study(self, *argv, crash_ids=(), stall_s=0):
        """Run the study in-process; return (archive rows, estimator calls)."""
        env = {
            "BUILD_WORKSPACE_DIRECTORY": self.root,
            "FAKE_CALLS": self.calls_path,
            "FAKE_CRASH_IDS": ",".join(crash_ids),
            "FAKE_STALL_S": str(stall_s),
        }
        old_env = {k: os.environ.get(k) for k in env}
        old_argv = sys.argv
        os.environ.update(env)
        sys.argv = ["optuna_study", self.exe, self.truth, "fake", *argv]
        try:
            optuna_study.main()
        finally:
            sys.argv = old_argv
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        with open(os.path.join(self.out_dir, "archive_fake.json")) as f:
            archive = json.load(f)
        calls = []
        if os.path.exists(self.calls_path):
            with open(self.calls_path) as f:
                calls = [json.loads(line) for line in f if line.strip()]
        return archive, calls

    # --- the batch walk ---

    def test_one_process_serves_a_whole_wave(self):
        """The point of batch mode: shared stages are paid once per wave."""
        archive, calls = self.run_study("--trials", "4", "--batch-size", "4")
        self.assertEqual(len(calls), 1, "a wave must not spawn a process per trial")
        self.assertEqual(len(archive), 4)

    def test_trials_are_cut_into_waves_of_batch_size(self):
        _, calls = self.run_study("--trials", "4", "--batch-size", "2")
        self.assertEqual(len(calls), 2)
        self.assertEqual([len(c["cfgs"]) for c in calls], [2, 2])

    def test_a_short_last_wave_is_not_padded(self):
        _, calls = self.run_study("--trials", "3", "--batch-size", "2")
        self.assertEqual([len(c["cfgs"]) for c in calls], [2, 1])

    def test_every_trial_reaches_the_estimator_as_its_own_config(self):
        archive, calls = self.run_study("--trials", "4", "--batch-size", "4")
        ids = set(calls[0]["cfgs"])
        self.assertEqual(ids, {str(row["number"]) for row in archive})
        for text in calls[0]["cfgs"].values():
            # The knob every trial samples, so a manifest that lost the
            # sampled env would show up here.
            self.assertIn("RUN_PLACE=", text)

    def test_archive_rows_carry_the_sampled_env_and_metrics(self):
        archive, _ = self.run_study("--trials", "2", "--batch-size", "2")
        for row in archive:
            self.assertIn("RUN_PLACE", row["env"])
            self.assertEqual(row["metrics"]["n_scored"], len(GROUND_TRUTH["paths"]))
            self.assertEqual(row["metrics"]["n_absent"], 0)
            for key in ("mean_rel_err", "bias", "spread", "kendall_tau"):
                self.assertIn(key, row["metrics"])

    def test_a_subtree_with_no_leaf_fails_its_trial_and_spares_the_rest(self):
        """A crashed or abandoned subtree must not take the wave with it."""
        archive, calls = self.run_study(
            "--trials", "4", "--batch-size", "4", crash_ids=("2",)
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(archive), 3)
        self.assertNotIn(2, [row["number"] for row in archive])

    def test_a_whole_wave_with_no_leaves_leaves_an_empty_archive(self):
        archive, _ = self.run_study(
            "--trials", "2", "--batch-size", "2", crash_ids=("0", "1")
        )
        self.assertEqual(archive, [])

    def test_batch_parallel_reaches_the_walk(self):
        _, calls = self.run_study(
            "--trials", "2", "--batch-size", "2", "--batch-parallel"
        )
        self.assertEqual(calls[0]["env_parallel"], None)
        argv = calls[0]["argv"]
        self.assertIn("EST_PARALLEL=1", argv)
        self.assertTrue(any(a.startswith("ORFS_FORK_JOBS=") for a in argv))

    def test_sequential_is_the_default(self):
        _, calls = self.run_study("--trials", "2", "--batch-size", "2")
        self.assertNotIn("EST_PARALLEL=1", calls[0]["argv"])

    def test_the_per_trial_budget_is_passed_as_the_subtree_timeout(self):
        _, calls = self.run_study(
            "--trials", "2", "--batch-size", "2", "--trial-timeout", "7"
        )
        self.assertIn("EST_SUBTREE_TIMEOUT=7.0", calls[0]["argv"])

    def test_waves_can_be_kept_for_wave_savings(self):
        keep = os.path.join(self.root, "waves")
        archive, _ = self.run_study(
            "--trials", "2", "--batch-size", "2", "--keep-waves", keep
        )
        leaves = sorted(os.listdir(os.path.join(keep, "wave_000")))
        self.assertEqual(leaves, ["0.json", "1.json"])
        self.assertEqual(len(archive), 2)

    # --- the legacy one-process-per-trial mode ---

    def test_without_batching_each_trial_is_its_own_process(self):
        archive, calls = self.run_study("--trials", "2", "--jobs", "1")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c["mode"] == "single" for c in calls))
        self.assertEqual(len(archive), 2)

    def test_a_trial_over_its_timeout_is_abandoned_not_fatal(self):
        archive, calls = self.run_study(
            "--trials", "1", "--jobs", "1", "--trial-timeout", "0.5", stall_s=5
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(archive, [])


if __name__ == "__main__":
    unittest.main()
