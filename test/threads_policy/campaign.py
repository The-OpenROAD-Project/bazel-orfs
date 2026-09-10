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

Runs happen outside the Bazel sandbox. Bazel builds the stage's inputs
and nothing else, so its own scheduling and caching never land inside a
measurement.

Two modes, because the two questions want opposite machines:

    --mode timing        one arm at a time, an idle machine asserted at
                         every arm start. #968, unchanged. A wall-clock
                         number is only a measurement under those
                         conditions.
    --mode idempotency   arms concurrently, each in its own
                         FLOW_VARIANT, no idle gate. Whether two arms
                         computed the same thing does not depend on how
                         busy the machine was, so the campaign finishes
                         in hours instead of days -- and the scheduling
                         perturbation is a feature, since contention is
                         what exposes an order-dependent bug. Timing
                         fields are recorded and marked contended, and
                         the report will not ladder them.

Every arm gets its own FLOW_VARIANT cloned from `base`, which is also
what makes it certain the arm ran: with the outputs absent, make cannot
decide the target is already up to date.

Resumable: one JSON per (design, stage, mode, arm, repeat), and an arm
whose file is already there is skipped. A campaign that costs hours must
survive being interrupted. A hang or a crash is recorded as a finding
with its stacks, not dropped -- an absence averages away.

    bazelisk run //test/threads_policy:campaign -- --mode idempotency \\
        --designs nangate45_gcd --stages cts --threads 1 2 4 8 16 --repeats 2
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time

from concurrent import futures

import deployment
import elapsed
import phases as phases_mod
import watchdog as watchdog_mod
import witness

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
    "asap7_gcd": "@orfs//flow/designs/asap7/gcd:gcd",
    # dense combinational, no macros
    "asap7_aes": "@orfs//flow/designs/asap7/aes:aes_cipher_top",
    # sequential CPU, deep clock tree
    "asap7_ibex": "@orfs//flow/designs/asap7/ibex:ibex_core",
    # larger datapath, long route
    "asap7_jpeg": "@orfs//flow/designs/asap7/jpeg:jpeg_encoder",
    # mid-size mixed
    "asap7_ethmac": "@orfs//flow/designs/asap7/ethmac:ethmac",
    # SRAM macros: a different placement and routing regime
    "asap7_tinyRocket": "@orfs//flow/designs/asap7/tinyRocket:RocketTile",
    # A second PDK. bazel-orfs#970 asks for sky130hd explicitly, and the
    # reason is not coverage for its own sake: a divergence that appears
    # on one PDK and not another is evidence about *which* code path
    # carries the bug, and one PDK cannot produce that evidence at all.
    # The corner, the cell library and the RC model all differ, so the
    # repair and CTS work is differently shaped even for the same RTL.
    "sky130hd_gcd": "@orfs//flow/designs/sky130hd/gcd:gcd",
    "sky130hd_ibex": "@orfs//flow/designs/sky130hd/ibex:ibex_core",
    "sky130hd_aes": "@orfs//flow/designs/sky130hd/aes:aes_cipher_top",
    # sky130hd's macro design, the counterpart to asap7/tinyRocket.
    "sky130hd_microwatt": "@orfs//flow/designs/sky130hd/microwatt:microwatt",
    # The OpenROAD#9781 reproducer: repair_timing's hash differed run to
    # run at 16 threads on nangate45/gcd and was identical at 1. Cheap
    # enough to run at every arm and every repeat, and the one design in
    # the set where a divergence has already been seen.
    "nangate45_gcd": "@orfs//flow/designs/nangate45/gcd:gcd",
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


def arm_ceiling(pin):
    """The highest thread count this host can actually install.

    `OpenRoad::setThreadCount` clamps its argument to
    `std::thread::hardware_concurrency()` and logs the clamped value,
    so a higher arm does not fail -- it runs, silently, as a duplicate
    of the ceiling arm. `collect()` catches that afterwards through the
    ORD-0030 witness, but only after the run has been paid for, and on
    a `route` arm that is hours.

    Measured: `NUM_CORES=32` on a 16-hardware-thread host logged
    "[INFO ORD-0030] Using 16 thread(s)". #968's ladder went to 32
    because it ran on a 32-thread host; the same command line on a
    smaller one produces two arms with the same thread count and a
    ladder with a flat top that looks like saturation.

    Under `--pin` the process is confined to one CPU per physical core,
    and `hardware_concurrency` reports the affinity mask, so the
    ceiling is the core count rather than the thread count.
    """
    if pin:
        cores = physical_cores()
        if cores:
            return cores
    return hardware_threads()


def check_arms(threads_arms, pin):
    """Refuse an arm the host cannot install, before anything runs."""
    ceiling = arm_ceiling(pin)
    too_high = sorted(t for t in threads_arms if t > ceiling)
    if too_high:
        raise SystemExit(
            "arms {} exceed this host's ceiling of {} thread(s){}: OpenROAD "
            "would clamp them and they would silently duplicate the t={} "
            "arm. Drop them, or run on a bigger host.".format(
                ", ".join(str(t) for t in too_high),
                ceiling,
                " under --pin" if pin else "",
                ceiling,
            )
        )
    if any(t < 1 for t in threads_arms):
        raise SystemExit("a thread count below 1 is not an arm")


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


def deploy_stage(target, stage, verbose):
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


# The `.sdc` each stage writes, from STAGE_METADATA's `result_names` in
# private/stages.bzl. Mirrored here for the same reason STAGE_SUBSTEPS
# is -- the runner drives make without a Starlark round trip -- and
# campaign_test.py asserts the copy against the source.
STAGE_SDC = {
    "place": "3_place.sdc",
    "cts": "4_cts.sdc",
    "grt": "5_1_grt.sdc",
    # None, not "5_route.sdc". STAGE_METADATA lists that file under
    # route's `result_names`, but it is written by the separate
    # `do-5_route.sdc` make target -- not by `do-5_2_route` or
    # `do-5_3_fillcell`, which is what an arm runs. Measured: a route
    # arm's variant directory holds 5_2_route.odb and 5_3_fillcell.odb
    # and no route .sdc.
    #
    # Recorded as "this stage has no .sdc witness" rather than as a
    # witness that went missing, and `collect` omits the field
    # entirely so the two cannot be confused. Adding the target to the
    # arm would create the witness, at the cost of measuring something
    # #968 did not.
    "route": None,
}


def run_arm(
    deploy,
    stage,
    threads,
    pin,
    verbose,
    variant,
    stamp_logs=True,
    watchdog_s=0,
    stacks_dir=None,
):
    """Run every substep of one stage at one thread count.

    The arm gets its own `FLOW_VARIANT`, cloned from `base`, so its
    results and logs cannot be confused with another arm's and several
    arms can run at once. It also means the arm always really runs:
    with the outputs absent, make cannot decide the target is already
    up to date.

    `pin` restricts the process to one CPU per physical core, which
    separates two claims that would otherwise be confounded: whether the
    win comes from asking for fewer threads, or from not landing two
    threads on one core's SMT siblings. `-threads` alone cannot deliver
    the second, so an upstream recommendation has to know which it is.

    Returns what happened rather than raising on a bad arm: a hang and
    a crash are both findings, and a campaign that drops them reports
    them as absences.
    """
    deploy.clone_base(variant)
    argv = []
    if pin:
        cores = physical_cores()
        if not cores:
            raise SystemExit("cannot pin: /proc/cpuinfo exposes no core topology")
        argv += ["taskset", "-c", "0-{}".format(cores - 1)]
    argv.append(os.path.join(deploy.root, "make"))
    argv += ["do-" + step for step in STAGE_SUBSTEPS[stage]]
    argv.append("NUM_CORES={}".format(threads))
    argv.append("FLOW_VARIANT={}".format(variant))
    if stamp_logs:
        # Elapsed-stamp every log line, which locates each phase in the
        # run and bounds the ones ORFS gives no `Took` line for. This
        # reaches the *stage* logs only because carried patch 0048 made
        # flow.sh honour RUN_CMD; before it, RUN_CMD governed the
        # peripheral logs and not the one anybody reads.
        argv.append(
            "RUN_CMD={} {}".format(
                sys.executable, os.path.join(workspace(), "log_timestamps.py")
            )
        )

    started = time.time()
    # Its own session, so the watchdog can kill `make`, the shell
    # wrappers and the tool with one killpg. Killing only make would
    # leave a hung OpenROAD holding its cores, and every arm measured
    # after it would be measuring that.
    process = subprocess.Popen(
        argv,
        cwd=deploy.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    hang = False
    stacks = None
    try:
        output, _ = process.communicate(timeout=watchdog_s or None)
    except subprocess.TimeoutExpired:
        hang = True
        if stacks_dir:
            os.makedirs(stacks_dir, exist_ok=True)
            stacks = watchdog_mod.capture(
                process.pid,
                os.path.join(stacks_dir, "{}_{}.stacks".format(stage, variant)),
            )
        watchdog_mod.kill_tree(process)
        output, _ = process.communicate()
    wall = time.time() - started

    if verbose or hang or process.returncode != 0:
        print(
            "      make wall {:.1f}s rc={} {}".format(
                wall, process.returncode, "HUNG" if hang else ""
            )
        )
    return {
        "wall_s": wall,
        "returncode": process.returncode,
        "hang": hang,
        "stacks": stacks,
        "output_tail": (output or "")[-4000:] if (hang or process.returncode) else None,
    }


def collect(deploy, stage, threads, variant, strict=True):
    """One sample per substep, with the knob and work witnesses checked.

    `strict` is off for an arm that hung or failed: there the point is
    to record whatever it did write, so the failure appears in the
    tables instead of as a gap.
    """
    logs = deploy.logs(variant)
    results = deploy.results(variant)
    samples = {}
    for step in STAGE_SUBSTEPS[stage]:
        path = os.path.join(logs, step + ".log")
        if not os.path.exists(path):
            if strict:
                raise SystemExit("{} left no log: the substep did not run".format(step))
            samples[step] = {"ran": False}
            continue
        got = elapsed.parse_log(path)
        got["ran"] = True

        # Assertion: the knob arrived. A timing number for the wrong
        # thread count is worse than a missing one, because it averages
        # in silently.
        if strict:
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
                k: v
                for k, v in metrics.items()
                if "fastroute" in k or k.endswith("__iter") or "runtime" in k.lower()
            }

        # The three witnesses (see witness.py). All computed here rather
        # than read from the log: ORFS's genElapsedTime.py writes no
        # summary row under a stamped log, so the log-derived hash
        # silently becomes None -- two documented ORFS mechanisms that
        # do not compose. The log value is kept where present so the
        # two can be compared, but the computed one is what the study
        # compares across arms.
        got["result_sha1_log"] = got.get("result_sha1")
        got["odb_sha1"] = witness.odb_sha1(results, step)
        # Absent key, not None: a stage that writes no `.sdc` from the
        # substeps an arm runs has no such witness, which is a
        # different statement from a witness that should exist and did
        # not. The verdict layer skips the first and calls the second
        # unproven.
        sdc_name = STAGE_SDC.get(stage)
        if sdc_name:
            got["sdc_sha1"] = witness.sdc_sha1(results, sdc_name)
        got["qor"] = witness.qor(logs, step)
        if got["odb_sha1"]:
            got["result_sha1"] = got["odb_sha1"]

        samples[step] = got
    return samples


# The two questions this campaign answers want opposite machines, so
# they are separate modes rather than one compromise.
#
# TIMING is #968 unchanged: one arm at a time, an idle machine asserted
# at every arm start, `taskset` available. A wall-clock number is only
# a measurement under those conditions -- a concurrent compile turned
# 1.8s of placement into 16.8s.
#
# IDEMPOTENCY asks whether two arms computed the same thing, which no
# amount of contention can change. So arms run concurrently, in their
# own variants, with no idle gate: the campaign finishes in hours
# instead of days, and the scheduling perturbation is a *feature* --
# contention is what exposes an order-dependent bug. Its timing fields
# are recorded and marked unusable, and the report refuses to put a
# contended sample in a ladder.
TIMING = "timing"
IDEMPOTENCY = "idempotency"
MODES = (TIMING, IDEMPOTENCY)


def default_jobs(mode, cores):
    """How many arms to run at once.

    Timing is one, always, and not a choice: see MODES. Idempotency
    defaults to a quarter of the cores, so an arm asking for the whole
    machine still gets a meaningful share while several are in flight.
    """
    if mode == TIMING:
        return 1
    return max(2, (cores or 2) // 4)


def result_path(results_dir, design, stage, mode, threads, pin, repeat):
    """One file per sample, so a campaign is resumable.

    `mode` is in the name because the same arm means different things
    in the two modes: an idempotency sample was measured under
    contention and must never be read as a timing sample.
    """
    return os.path.join(
        results_dir,
        "{}_{}_{}_t{}{}_r{}.json".format(
            design, stage, mode, threads, "_pinned" if pin else "", repeat
        ),
    )


def one_arm(deploy, design, stage, threads, repeat, args, prov, mode, jobs):
    """Run one arm and return its record. Never raises on a bad arm."""
    variant = deployment.arm_variant(threads, repeat)
    load = loadavg1()
    if mode == TIMING:
        # Assertion: the machine is idle. A neighbour's build inside a
        # measurement is indistinguishable from a thread effect. The
        # deploy is usually what has to drain, so wait rather than
        # refuse.
        load = wait_for_idle(args.max_load)

    print(
        "  {} threads={}{} repeat={} (load {:.2f})".format(
            mode, threads, " pinned" if args.pin else "", repeat, load
        )
    )
    outcome = run_arm(
        deploy,
        stage,
        threads,
        args.pin,
        args.verbose,
        variant,
        stamp_logs=not args.no_stamp_logs,
        watchdog_s=args.watchdog_s,
        stacks_dir=args.stacks_dir,
    )
    ok = outcome["returncode"] == 0 and not outcome["hang"]
    samples = collect(deploy, stage, threads, variant, strict=ok)
    return {
        "design": design,
        "platform": deploy.platform,
        "target": DESIGNS[design],
        "stage": stage,
        "mode": mode,
        "variant": variant,
        "threads": threads,
        "pinned": args.pin,
        "repeat": repeat,
        "jobs": jobs,
        # A timing number taken while other arms were running measures
        # the other arms. Recorded, flagged, and never laddered.
        "contended": jobs > 1,
        "loadavg_at_start": load,
        "make_wall_s": outcome["wall_s"],
        "returncode": outcome["returncode"],
        "hang": outcome["hang"],
        "stacks": outcome["stacks"],
        "output_tail": outcome["output_tail"],
        "substeps": samples,
        "provenance": prov,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--designs", nargs="+", default=sorted(DESIGNS), choices=sorted(DESIGNS)
    )
    parser.add_argument(
        "--stages",
        nargs="+",
        default=["place", "cts", "grt", "route"],
        choices=sorted(STAGE_SUBSTEPS),
    )
    parser.add_argument(
        "--mode",
        default=TIMING,
        choices=MODES,
        help="timing: one arm at a time on an idle machine (#968). "
        "idempotency: arms concurrently, contention on purpose.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="arms to run at once; forced to 1 in timing mode",
    )
    parser.add_argument(
        "--threads",
        nargs="+",
        type=int,
        default=None,
        help="thread counts to measure; default is cores and hw threads",
    )
    parser.add_argument(
        "--pin", action="store_true", help="taskset to one CPU per core"
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--max-load",
        type=float,
        default=1.0,
        help="refuse to record if 1-minute loadavg exceeds this at arm start",
    )
    parser.add_argument(
        "--watchdog-s",
        type=int,
        default=0,
        help="dump stacks and kill an arm still running after this many "
        "seconds; 0 disables. A hang is recorded as a finding.",
    )
    parser.add_argument("--stacks-dir", default=None)
    parser.add_argument("--results", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--no-stamp-logs",
        action="store_true",
        help="do not override RUN_CMD; drops per-phase elapsed stamps. Use "
        "to check whether stamping perturbs the timing it measures.",
    )
    args = parser.parse_args()

    threads_arms = args.threads
    if threads_arms is None:
        cores = physical_cores()
        threads_arms = sorted({cores, hardware_threads()} - {None})
    check_arms(threads_arms, args.pin)

    jobs = args.jobs or default_jobs(args.mode, physical_cores())
    if args.mode == TIMING and jobs != 1:
        raise SystemExit(
            "--jobs {} in timing mode: a wall-clock number taken while "
            "another arm is running measures the other arm. Use --mode "
            "idempotency, where contention is the point.".format(jobs)
        )

    results_dir = args.results or os.path.join(
        workspace(), "tmp", "threads_policy", "results"
    )
    os.makedirs(results_dir, exist_ok=True)
    if args.stacks_dir is None:
        args.stacks_dir = os.path.join(os.path.dirname(results_dir), "stacks")

    prov = provenance()
    print(
        "host: {} cores / {} hw threads, governor {}, boost {}".format(
            prov["physical_cores"],
            prov["hardware_threads"],
            prov["governor"],
            prov["boost"],
        )
    )
    print(
        "arms: mode={} threads={} pin={} repeats={} jobs={}".format(
            args.mode, threads_arms, args.pin, args.repeats, jobs
        )
    )
    print("results: {}".format(results_dir))

    written = 0
    skipped = 0
    failed = 0
    undeployable = []
    for design in args.designs:
        for stage in args.stages:
            wanted = [
                (t, r)
                for t in threads_arms
                for r in range(1, args.repeats + 1)
                if not os.path.exists(
                    result_path(results_dir, design, stage, args.mode, t, args.pin, r)
                )
            ]
            if not wanted:
                skipped += len(threads_arms) * args.repeats
                continue

            print("\n=== {} {}".format(design, stage))
            # A design this repo has never built, or a stage that fails
            # to build, must not end a campaign that has hours of other
            # arms still to run. Reported loudly and skipped; a resumed
            # run retries it, since nothing was recorded.
            try:
                deploy = deployment.Deployment(
                    deploy_stage(DESIGNS[design], stage, args.verbose)
                )
            except SystemExit as error:
                print("  SKIPPED: {}".format(error))
                undeployable.append("{} {}: {}".format(design, stage, error))
                continue

            def record_arm(arm):
                threads, repeat = arm
                record = one_arm(
                    deploy, design, stage, threads, repeat, args, prov, args.mode, jobs
                )
                path = result_path(
                    results_dir, design, stage, args.mode, threads, args.pin, repeat
                )
                with open(path, "w") as handle:
                    json.dump(record, handle, indent=2, sort_keys=True)
                return record

            if jobs == 1:
                records = [record_arm(arm) for arm in wanted]
            else:
                with futures.ThreadPoolExecutor(max_workers=jobs) as pool:
                    records = list(pool.map(record_arm, wanted))

            for record in records:
                written += 1
                if record["hang"] or record["returncode"]:
                    failed += 1
                    print(
                        "      t{} r{}: {}{}".format(
                            record["threads"],
                            record["repeat"],
                            (
                                "HUNG"
                                if record["hang"]
                                else "rc=%s" % record["returncode"]
                            ),
                            (
                                " stacks: %s" % record["stacks"]
                                if record["stacks"]
                                else ""
                            ),
                        )
                    )
                    continue
                for step, got in record["substeps"].items():
                    print(
                        "      t{} r{} {:<22} {:>8.2f}s  {:>5}% cpu  {}".format(
                            record["threads"],
                            record["repeat"],
                            step,
                            got["wall_s"],
                            got["cpu_pct"],
                            got.get("odb_sha1") or "no odb",
                        )
                    )

    print(
        "\nwrote {} arm(s), {} of them failed or hung, skipped {} already "
        "present".format(written, failed, skipped)
    )
    if undeployable:
        # Named individually, because "8 stages did not build" hides
        # which design is missing from every table that follows.
        print("\n{} (design, stage) pair(s) never deployed:".format(len(undeployable)))
        for line in undeployable:
            print("  {}".format(line))
    print("results in {}".format(results_dir))


if __name__ == "__main__":
    main()
