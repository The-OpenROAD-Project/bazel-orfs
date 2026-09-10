#!/usr/bin/env python3
"""Run one arm of the thread-policy campaign and record what it cost.

ORFS gives OpenROAD `-threads $(NUM_CORES)` and derives NUM_CORES from
`nproc`, which counts *hardware threads* (flow/scripts/variables.mk).
On an SMT machine that is twice the core count. This runner measures
whether the second half of those threads pays for itself, per substep.

    stage inputs   built by bazel, once, and identical for every arm
    the arm        <deploy>/make do-<substep>... NUM_CORES=<n>
    the reading    the log lines ORFS already writes (see elapsed.py)

Each arm is one stage's substeps in a single `make` invocation, which is
how ORFS runs them: they chain, and running them together is the only
way the later ones get the inputs they expect. Every substep still
writes its own log, so one arm yields one sample per substep.

Runs happen outside the Bazel sandbox, one at a time. Bazel builds the
stage's inputs and nothing else, so its own scheduling and caching never
land inside a measurement.

Resumable: one JSON per (design, stage, arm, repeat), and an arm whose
file is already there is skipped. A campaign that costs hours must
survive being interrupted.

    bazelisk run //test/threads_policy:campaign -- --phase 2
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

import hashlib

import elapsed
import phases as phases_mod

# Mirrors STAGE_SUBSTEPS in private/stages.bzl, which is the single
# source of truth. campaign_test.py asserts the two are equal, so this
# copy cannot drift from the flow it drives.
STAGE_SUBSTEPS = {
    "place": [
        "3_1_place_gp_skip_io",
        "3_2_place_iop",
        "3_3_place_gp",
        "3_4_place_resized",
        "3_5_place_dp",
    ],
    "cts": ["4_1_cts"],
    "grt": ["5_1_grt"],
    "route": ["5_2_route", "5_3_fillcell"],
}

# The design set, and why each one is in it. Spread is the point: a
# claim about thread policy drawn from one design shape would not
# survive contact with a different one.
DESIGNS = {
    # tiny: the control. Startup cost dominates, so threads cannot
    # matter here, and a "speedup" on gcd would indict the method.
    "gcd": "@orfs//flow/designs/asap7/gcd:gcd",
    # dense combinational, no macros
    "aes": "@orfs//flow/designs/asap7/aes:aes_cipher_top",
    # sequential CPU, deep clock tree
    "ibex": "@orfs//flow/designs/asap7/ibex:ibex_core",
    # larger datapath, long route
    "jpeg": "@orfs//flow/designs/asap7/jpeg:jpeg_encoder",
    # mid-size mixed
    "ethmac": "@orfs//flow/designs/asap7/ethmac:ethmac",
    # SRAM macros: a different placement and routing regime
    "tinyRocket": "@orfs//flow/designs/asap7/tinyRocket:RocketTile",
}

# Physical cores and hardware threads on the measurement host. The whole
# study is the difference between these two numbers, so they are read
# from the machine rather than assumed.
def hardware_threads():
    return os.sysconf("SC_NPROCESSORS_ONLN")


def physical_cores():
    """Distinct (physical id, core id) pairs in /proc/cpuinfo.

    This is also the derivation the proposed upstream change would use,
    so measuring with it keeps the study honest about what it proposes:
    no lscpu, no new dependency, and a documented fallback when the
    topology is not exposed (ARM, some containers) -- there, hardware
    threads is the only answer available and also the right one, since
    without SMT the two counts coincide.
    """
    package = None
    pairs = set()
    try:
        with open("/proc/cpuinfo") as handle:
            for line in handle:
                if line.startswith("physical id"):
                    package = line.split(":", 1)[1].strip()
                elif line.startswith("core id"):
                    pairs.add((package, line.split(":", 1)[1].strip()))
    except OSError:
        return None
    return len(pairs) or None


def loadavg1():
    return os.getloadavg()[0]


def wait_for_idle(threshold, timeout_s=900, poll_s=15):
    """Block until the 1-minute load average drops below `threshold`.

    Deploying a stage builds its inputs with bazel at full parallelism,
    which leaves the load average high for a minute or so afterwards.
    Timing a run into that tail measures the tail. Refusing outright
    would be useless -- the campaign would stop on its own prep -- so
    wait for the machine to settle instead, and only give up if it never
    does, which means something else is running and the numbers would be
    noise either way.

    Returns the load it settled at; raises SystemExit on timeout.
    """
    deadline = time.time() + timeout_s
    load = loadavg1()
    while load > threshold:
        if time.time() > deadline:
            raise SystemExit(
                "load average {:.2f} still above {:.2f} after {}s: something "
                "else is running and these timings would be noise".format(
                    load, threshold, timeout_s
                )
            )
        time.sleep(poll_s)
        load = loadavg1()
    return load


def provenance():
    """What about this machine and toolchain could move a timing number.

    Recorded with every sample, because a wall-clock measurement without
    it is not reproducible and not challengeable.
    """
    def read(path):
        try:
            with open(path) as handle:
                return handle.read().strip()
        except OSError:
            return None

    return {
        "hardware_threads": hardware_threads(),
        "physical_cores": physical_cores(),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in (read("/proc/cpuinfo") or "").splitlines()
                if line.startswith("model name")
            ),
            None,
        ),
        "governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "boost": read("/sys/devices/system/cpu/cpufreq/boost"),
        "kernel": platform.release(),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
    }


def workspace():
    """The repo root, whether run via bazel or directly."""
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()


_INSTALLED = re.compile(r"Reproducer installed to: (.+)$", re.M)


def deploy(target, stage, verbose):
    """Build the stage's inputs and install the reproducer; return its dir.

    `<target>_<stage>_deps` is a runnable that deploys under ./tmp (see
    create_deps_tar in private/rules.bzl). It is used directly rather
    than through //:deps, whose wrapper looks for a .tar.gz among the
    _deps outputs -- the tar is the separate _deps_tar target, so that
    path fails for every target. Reported separately; not this study's
    to fix.
    """
    label = "{}_{}_deps".format(target, stage)
    out = subprocess.run(
        ["bazelisk", "run", label],
        cwd=workspace(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if out.returncode != 0:
        sys.stderr.write(out.stdout[-4000:])
        raise SystemExit("deploy failed: {}".format(label))
    found = _INSTALLED.findall(out.stdout)
    if not found:
        raise SystemExit(
            "deploy printed no install path for {} -- the _deps rule's "
            "output shape changed".format(label)
        )
    if verbose:
        print("  deployed: {}".format(found[-1]))
    return found[-1].strip()


def log_dir(deploy_dir):
    """The one logs/<platform>/<design>/<variant> dir under a deployment."""
    hits = []
    for root, dirs, _ in os.walk(deploy_dir):
        if os.path.basename(root) == "logs":
            for variant_root, _, files in os.walk(root):
                if any(f.endswith(".log") or f.endswith(".tmp.log") for f in files):
                    hits.append(variant_root)
            # A deployment holds exactly one logs tree.
            dirs[:] = []
    if not hits:
        raise SystemExit("no log directory under {}".format(deploy_dir))
    return sorted(hits, key=len)[-1]


def results_dir(deploy_dir):
    """The results/<platform>/<design>/<variant> dir of a deployment."""
    hits = []
    for root, dirs, files in os.walk(deploy_dir):
        if os.path.basename(root) == "results":
            for variant_root, _, names in os.walk(root):
                if any(n.endswith(".odb") for n in names):
                    hits.append(variant_root)
            dirs[:] = []
    if not hits:
        return None
    return sorted(hits, key=len)[-1]


def result_hash(deploy_dir, step):
    """sha1 of a substep's own .odb, computed here rather than read.

    ORFS's genElapsedTime.py normally appends a summary row carrying
    this, and reading it was cheaper than recomputing. But that parser
    does `line.replace("Elapsed time: ", "")` and so cannot read a
    stamped log: with RUN_CMD pointed at log_timestamps.py it emits no
    row at all, and the witness silently becomes None. Two documented
    ORFS mechanisms that do not compose -- reported, not worked around
    in ORFS.

    So the identical-work witness is computed directly. It no longer
    depends on which logging mode the arm ran in, which is what a
    witness has to be: the same question asked the same way in every
    arm.
    """
    rdir = results_dir(deploy_dir)
    if not rdir:
        return None
    path = os.path.join(rdir, step + ".odb")
    if not os.path.exists(path):
        return None
    hasher = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    # Same 20-hex-character prefix ORFS's own summary uses, so the two
    # remain comparable.
    return hasher.hexdigest()[:20]


def run_arm(deploy_dir, stage, threads, pin, verbose, stamp_logs=True):
    """Run every substep of one stage at one thread count.

    `pin` restricts the process to one CPU per physical core, which
    separates two claims that would otherwise be confounded: whether the
    win comes from asking for fewer threads, or from not landing two
    threads on one core's SMT siblings. `-threads` alone cannot deliver
    the second, so an upstream recommendation has to know which it is.
    """
    argv = []
    if pin:
        cores = physical_cores()
        if not cores:
            raise SystemExit("cannot pin: /proc/cpuinfo exposes no core topology")
        argv += ["taskset", "-c", "0-{}".format(cores - 1)]
    argv.append(os.path.join(deploy_dir, "make"))
    argv += ["do-" + step for step in STAGE_SUBSTEPS[stage]]
    argv.append("NUM_CORES={}".format(threads))
    if stamp_logs:
        # Elapsed-stamp every log line, which locates each phase in the
        # run and bounds the ones ORFS gives no `Took` line for. This
        # reaches the *stage* logs only because carried patch 0048 made
        # flow.sh honour RUN_CMD; before it, RUN_CMD governed the
        # peripheral logs and not the one anybody reads.
        argv.append("RUN_CMD={} {}".format(
            sys.executable, os.path.join(workspace(), "log_timestamps.py")))

    started = time.time()
    out = subprocess.run(
        argv,
        cwd=deploy_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wall = time.time() - started
    if out.returncode != 0:
        sys.stderr.write(out.stdout[-6000:])
        raise SystemExit(
            "arm failed: {} threads={} pin={}".format(stage, threads, pin)
        )
    if verbose:
        print("      make wall {:.1f}s".format(wall))
    return wall


def collect(deploy_dir, stage, threads):
    """One sample per substep, with the knob and work witnesses checked."""
    logs = log_dir(deploy_dir)
    samples = {}
    for step in STAGE_SUBSTEPS[stage]:
        path = os.path.join(logs, step + ".log")
        if not os.path.exists(path):
            raise SystemExit(
                "{} left no log: the substep did not run".format(step)
            )
        got = elapsed.parse_log(path)

        # Assertion: the knob arrived. A timing number for the wrong
        # thread count is worse than a missing one, because it averages
        # in silently.
        if got["threads"] is None:
            raise SystemExit(
                "{}: no ORD-0030 line, so the thread count is unproven".format(step)
            )
        if got["threads"] != threads:
            raise SystemExit(
                "{}: asked for {} threads, OpenROAD installed {}".format(
                    step, threads, got["threads"]
                )
            )
        # The phase stack: which regions inside this substep spent the
        # time. A substep number averages regions that want opposite
        # thread counts, and an average is not a policy.
        with open(path, errors="replace") as handle:
            text = handle.read()
        parsed = phases_mod.parse_phases(text)
        got["phases"] = parsed["phases"]
        got["nested"] = parsed["nested"]
        got["stamped"] = parsed["stamped"]

        # Assertion: the stack accounts for the wall time. A stack that
        # does not add up is a mis-parse, and is recorded as such rather
        # than balanced by adjusting a number.
        got["reconcile"] = phases_mod.reconcile(parsed, got["wall_s"])

        # grt already emits ~18 phase timers of its own; they cost
        # nothing to carry and are the FastRoute-internal view the
        # `Took` lines cannot give.
        metrics_path = os.path.join(logs, step + ".json")
        if os.path.exists(metrics_path):
            try:
                with open(metrics_path) as handle:
                    metrics = json.load(handle)
            except ValueError:
                metrics = {}
            got["tool_metrics"] = {
                k: v for k, v in metrics.items()
                if "fastroute" in k or k.endswith("__iter") or "runtime" in k.lower()
            }

        # Identical-work witness, computed rather than read; see
        # result_hash(). The log-derived value is kept when present so
        # the two can be compared, but the computed one is what the
        # study compares across arms.
        got["result_sha1_log"] = got.get("result_sha1")
        computed = result_hash(deploy_dir, step)
        if computed:
            got["result_sha1"] = computed

        samples[step] = got
    return samples


def result_path(results_dir, design, stage, threads, pin, repeat):
    return os.path.join(
        results_dir,
        "{}_{}_t{}{}_r{}.json".format(
            design, stage, threads, "_pinned" if pin else "", repeat
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--designs", nargs="+", default=sorted(DESIGNS), choices=sorted(DESIGNS)
    )
    parser.add_argument(
        "--stages", nargs="+", default=["place", "cts", "grt", "route"],
        choices=sorted(STAGE_SUBSTEPS),
    )
    parser.add_argument(
        "--threads", nargs="+", type=int, default=None,
        help="thread counts to measure; default is cores and hw threads",
    )
    parser.add_argument("--pin", action="store_true", help="taskset to one CPU per core")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--max-load", type=float, default=1.0,
        help="refuse to record if 1-minute loadavg exceeds this at arm start",
    )
    parser.add_argument("--results", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--no-stamp-logs", action="store_true",
        help="do not override RUN_CMD; drops per-phase elapsed stamps. Use "
             "to check whether stamping perturbs the timing it measures.",
    )
    args = parser.parse_args()

    threads_arms = args.threads
    if threads_arms is None:
        cores = physical_cores()
        threads_arms = sorted({cores, hardware_threads()} - {None})

    results_dir = args.results or os.path.join(
        workspace(), "tmp", "threads_policy", "results"
    )
    os.makedirs(results_dir, exist_ok=True)

    prov = provenance()
    print("host: {} cores / {} hw threads, governor {}, boost {}".format(
        prov["physical_cores"], prov["hardware_threads"],
        prov["governor"], prov["boost"]))
    print("arms: threads={} pin={} repeats={}".format(
        threads_arms, args.pin, args.repeats))
    print("results: {}".format(results_dir))

    written = 0
    skipped = 0
    for design in args.designs:
        for stage in args.stages:
            wanted = [
                (t, r)
                for t in threads_arms
                for r in range(1, args.repeats + 1)
                if not os.path.exists(
                    result_path(results_dir, design, stage, t, args.pin, r)
                )
            ]
            if not wanted:
                skipped += len(threads_arms) * args.repeats
                continue

            print("\n=== {} {}".format(design, stage))
            deploy_dir = deploy(DESIGNS[design], stage, args.verbose)

            for threads, repeat in wanted:
                # Assertion: the machine is idle. A neighbour's build
                # inside a measurement is indistinguishable from a
                # thread effect. The deploy above is usually what has to
                # drain, so wait rather than refuse.
                load = wait_for_idle(args.max_load)

                print("  threads={}{} repeat={} (load {:.2f})".format(
                    threads, " pinned" if args.pin else "", repeat, load))
                make_wall = run_arm(
                    deploy_dir, stage, threads, args.pin, args.verbose,
                    stamp_logs=not args.no_stamp_logs,
                )
                samples = collect(deploy_dir, stage, threads)

                record = {
                    "design": design,
                    "target": DESIGNS[design],
                    "stage": stage,
                    "threads": threads,
                    "pinned": args.pin,
                    "repeat": repeat,
                    "loadavg_at_start": load,
                    "make_wall_s": make_wall,
                    "substeps": samples,
                    "provenance": prov,
                    "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                path = result_path(
                    results_dir, design, stage, threads, args.pin, repeat
                )
                with open(path, "w") as handle:
                    json.dump(record, handle, indent=2, sort_keys=True)
                written += 1
                for step, got in samples.items():
                    print("      {:<22} {:>8.2f}s  {:>5}% cpu".format(
                        step, got["wall_s"], got["cpu_pct"]))

    print("\nwrote {} arm(s), skipped {} already present".format(written, skipped))
    print("results in {}".format(results_dir))


if __name__ == "__main__":
    main()
