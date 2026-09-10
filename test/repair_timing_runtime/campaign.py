#!/usr/bin/env python3
"""Run one arm of the repair_timing runtime campaign and record what it cost.

repair_timing is three quarters of a cts or grt stage on the designs
where it grinds, and it grinds with `-verbose`, so every design in the
flow already writes its whole trajectory into the log. This runner
builds a stage's inputs once with bazel, runs the stage outside the
sandbox with one knob changed, and reads what the tool wrote:

    stage inputs   built by bazel, once, identical for every arm
    the arm        <deploy>/make do-<substep>... KNOB=value ...
    the reading    repair.py (the repair_timing trajectory and runtimes),
                   elapsed.py (wall, CPU, peak RSS, thread witness),
                   phases.py (the `Took` stack around them)

An arm is a name and a dict of ORFS variables given to make on its
command line. GNU make exports command-line variables to every recipe,
so they reach openroad's environment and override a design config.mk's
`export TNS_END_PERCENT = 100` alike; the echoed `repair_timing ...`
line in the log is the witness that the tool was asked what the arm
meant, and repair.py records it with every sample.

Thread count is fixed at the physical core count and the process is
pinned to one CPU per core. Thread policy is another study's question;
here it is held still.

Resumable: one JSON per (design, stage, arm, repeat), and an arm whose
file is already there is skipped. A campaign that costs hours must
survive being interrupted.

    bazelisk run //test/repair_timing_runtime:campaign -- --stages cts grt
"""

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time

import elapsed
import phases as phases_mod
import repair

# Mirrors STAGE_SUBSTEPS in private/stages.bzl, which is the single
# source of truth. campaign_test.py asserts the two are equal, so this
# copy cannot drift from the flow it drives.
STAGE_SUBSTEPS = {
    "floorplan": [
        "2_1_floorplan",
        "2_2_floorplan_macro",
        "2_3_floorplan_tapcell",
        "2_4_floorplan_pdn",
    ],
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

# Every asap7 design the config.mk DSL wires up, by directory name. The
# census runs all of them; the arms run the ones the census shows
# grinding. minimal has no netlist; the aes-block and mock-sram
# sub-blocks are reached through their parents.
DESIGNS = {
    "aes": "@orfs//flow/designs/asap7/aes:aes_cipher_top",
    "aes-block": "@orfs//flow/designs/asap7/aes-block:aes_cipher_top",
    "aes-mbff": "@orfs//flow/designs/asap7/aes-mbff:aes_cipher_top",
    "aes_lvt": "@orfs//flow/designs/asap7/aes_lvt:aes_cipher_top",
    "coralnpu": "@orfs//flow/designs/asap7/coralnpu:CoreMiniAxi",
    "cva6": "@orfs//flow/designs/asap7/cva6:cva6",
    "ethmac": "@orfs//flow/designs/asap7/ethmac:ethmac",
    "ethmac_lvt": "@orfs//flow/designs/asap7/ethmac_lvt:ethmac",
    "gcd": "@orfs//flow/designs/asap7/gcd:gcd",
    "gcd-ccs": "@orfs//flow/designs/asap7/gcd-ccs:gcd",
    "ibex": "@orfs//flow/designs/asap7/ibex:ibex_core",
    "jpeg": "@orfs//flow/designs/asap7/jpeg:jpeg_encoder",
    "jpeg_lvt": "@orfs//flow/designs/asap7/jpeg_lvt:jpeg_encoder",
    "mock-alu": "@orfs//flow/designs/asap7/mock-alu:MockAlu",
    "mock-cpu": "@orfs//flow/designs/asap7/mock-cpu:mock_cpu",
    "riscv32i": "@orfs//flow/designs/asap7/riscv32i:riscv_top",
    "riscv32i-mock-sram": "@orfs//flow/designs/asap7/riscv32i-mock-sram:riscv_top",
    "swerv_wrapper": "@orfs//flow/designs/asap7/swerv_wrapper:swerv_wrapper",
    "tinyRocket": "@orfs//flow/designs/asap7/tinyRocket:RocketTile",
    "uart": "@orfs//flow/designs/asap7/uart:uart",
}

# The arms: a name, and the make variables that make it different from
# the design's own config.mk. `base` is the census and the control.
# Knob arms are zero-code levers ORFS already exposes; a patch arm is
# the same `base` dict run against a binary the module graph built with
# a carried patch, selected with --openroad.
ARMS = {
    "base": {},
    "tns20": {"TNS_END_PERCENT": "20"},
    "tns5": {"TNS_END_PERCENT": "5"},
    "nogasp": {"SKIP_LAST_GASP": "1"},
    "noclone": {"SKIP_GATE_CLONING": "1"},
    "nounbuf": {"SKIP_BUFFER_REMOVAL": "1"},
    "footprint": {"MATCH_CELL_FOOTPRINT": "1"},
    "nopostwns": {"OPT_POST_GRT_WNS": "0"},
}


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


def other_openroad_pids(pattern="(^|/)openroad( |$)"):
    """PIDs of openroad processes on the host, none of them ours.

    The load-average gate cannot see a single-threaded neighbour:
    repair_timing is mostly serial, so a whole other campaign's arm
    shows as a load of about one, and the 1-minute average dips under
    the threshold between its phases. This study lost a repeat to
    exactly that overlap, so the gate also asks the process table.
    """
    out = subprocess.run(
        ["pgrep", "-f", pattern], stdout=subprocess.PIPE, text=True
    )
    return [int(pid) for pid in out.stdout.split() if pid.strip()]


def wait_for_no_openroad(timeout_s=7200, poll_s=30):
    """Block until no other openroad process is running; SystemExit on timeout."""
    deadline = time.time() + timeout_s
    pids = other_openroad_pids()
    while pids:
        if time.time() > deadline:
            raise SystemExit(
                "openroad still running elsewhere (pids {}) after {}s: another "
                "campaign or flow is on this machine and these timings would "
                "be noise".format(pids, timeout_s)
            )
        time.sleep(poll_s)
        pids = other_openroad_pids()


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


def run_arm(deploy_dir, stage, threads, overrides, openroad_exe, verbose):
    """Run every substep of one stage with the arm's variables.

    Pinned to one CPU per physical core, always: thread policy is held
    still so that what moves is the knob.
    """
    cores = physical_cores()
    if not cores:
        raise SystemExit("cannot pin: /proc/cpuinfo exposes no core topology")
    argv = ["taskset", "-c", "0-{}".format(cores - 1)]
    argv.append(os.path.join(deploy_dir, "make"))
    argv += ["do-" + step for step in STAGE_SUBSTEPS[stage]]
    argv.append("NUM_CORES={}".format(threads))
    for key, value in sorted(overrides.items()):
        argv.append("{}={}".format(key, value))
    # Elapsed-stamp every log line, so the repair trajectory is a time
    # series and not just an iteration count.
    argv.append(
        "RUN_CMD={} {}".format(
            sys.executable, os.path.join(workspace(), "log_timestamps.py")
        )
    )
    env = dict(os.environ)
    if openroad_exe:
        # The deployed make wrapper lets a caller-supplied OPENROAD_EXE
        # win; this is how a patch arm runs a binary the module graph
        # built with a carried patch (bazelisk build @openroad//:openroad).
        env["OPENROAD_EXE"] = openroad_exe

    started = time.time()
    out = subprocess.run(
        argv,
        cwd=deploy_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wall = time.time() - started
    if out.returncode != 0:
        sys.stderr.write(out.stdout[-6000:])
        raise SystemExit("arm failed: {} {}".format(stage, overrides))
    if verbose:
        print("      make wall {:.1f}s".format(wall))
    return wall


def collect(deploy_dir, stage, threads, overrides):
    """One sample per substep, with the knob and work witnesses checked."""
    logs = log_dir(deploy_dir)
    samples = {}
    for step in STAGE_SUBSTEPS[stage]:
        path = os.path.join(logs, step + ".log")
        if not os.path.exists(path):
            raise SystemExit("{} left no log: the substep did not run".format(step))
        got = elapsed.parse_log(path)
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
        with open(path, errors="replace") as handle:
            text = handle.read()
        parsed = phases_mod.parse_phases(text)
        got["phases"] = parsed["phases"]
        got["stamped"] = parsed["stamped"]
        got["reconcile"] = phases_mod.reconcile(parsed, got["wall_s"])

        # The repair trajectory, and the knob witness on every call.
        calls = repair.parse_log(text)
        got["repair"] = repair.summarize(calls)
        got["repair_rows"] = [c["rows"] for c in calls]
        check_witness(step, got["repair"], overrides)

        got["result_sha1_log"] = got.get("result_sha1")
        computed = result_hash(deploy_dir, step)
        if computed:
            got["result_sha1"] = computed
        samples[step] = got
    return samples


# ORFS variable -> the repair_timing argument it becomes (util.tcl).
WITNESS = {
    "TNS_END_PERCENT": ("repair_tns", False),
    "SKIP_LAST_GASP": ("skip_last_gasp", True),
    "SKIP_GATE_CLONING": ("skip_gate_cloning", True),
    "SKIP_BUFFER_REMOVAL": ("skip_buffer_removal", True),
    "SKIP_PIN_SWAP": ("skip_pin_swap", True),
    "SKIP_VT_SWAP": ("skip_vt_swap", True),
    "MATCH_CELL_FOOTPRINT": ("match_cell_footprint", True),
    "SETUP_SLACK_MARGIN": ("setup_margin", False),
    "HOLD_SLACK_MARGIN": ("hold_margin", False),
}


def check_witness(step, summaries, overrides):
    """The echoed repair_timing line must say what the arm asked for.

    Only the helper's setup+hold call is checked: the floorplan and
    post-grt calls hard-code their own arguments and legitimately ignore
    most knobs. OPT_POST_GRT_WNS=0 is witnessed by the post_grt_wns call
    being absent.
    """
    main = [s for s in summaries if s["kind"] == "setup_hold"]
    if not main and any(k in WITNESS for k in overrides):
        raise SystemExit("{}: no setup+hold repair_timing call to witness".format(step))
    for summary in main:
        args = summary["witness"]
        for var, value in overrides.items():
            if var not in WITNESS:
                continue
            flag, is_flag = WITNESS[var]
            if is_flag:
                want = value not in ("", "0")
                if bool(args.get(flag)) != want:
                    raise SystemExit(
                        "{}: {}={} but repair_timing {} -{}".format(
                            step, var, value, "has" if args.get(flag) else "lacks", flag
                        )
                    )
            elif str(args.get(flag)) != str(value):
                raise SystemExit(
                    "{}: {}={} but repair_timing -{} {}".format(
                        step, var, value, flag, args.get(flag)
                    )
                )
    if overrides.get("OPT_POST_GRT_WNS") == "0" and step == "5_1_grt":
        if any(s["kind"] == "post_grt_wns" for s in summaries):
            raise SystemExit("5_1_grt: OPT_POST_GRT_WNS=0 but the post-grt call ran")


def result_path(results_dir, design, stage, arm, repeat):
    return os.path.join(results_dir, "{}_{}_{}_r{}.json".format(design, stage, arm, repeat))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--designs", nargs="+", default=sorted(DESIGNS), choices=sorted(DESIGNS)
    )
    parser.add_argument(
        "--stages", nargs="+", default=["floorplan", "cts", "grt"],
        choices=sorted(STAGE_SUBSTEPS),
    )
    parser.add_argument("--arms", nargs="+", default=["base"], choices=sorted(ARMS))
    parser.add_argument(
        "--arm-suffix", default="",
        help="appended to the arm name in result files; names a binary "
             "(e.g. -p0066) when --openroad points at a patched build",
    )
    parser.add_argument(
        "--openroad", default=None,
        help="OPENROAD_EXE to run the arm with instead of the deployed one",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--max-load", type=float, default=1.0,
        help="refuse to record if 1-minute loadavg exceeds this at arm start",
    )
    parser.add_argument("--results", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--keep-going", action="store_true",
        help="record a failed arm as such and continue with the next design",
    )
    args = parser.parse_args()

    threads = physical_cores()
    if not threads:
        raise SystemExit("cannot read the core count from /proc/cpuinfo")

    results_dir = args.results or os.path.join(
        workspace(), "tmp", "repair_timing_runtime", "results"
    )
    os.makedirs(results_dir, exist_ok=True)

    prov = provenance()
    prov["openroad_exe"] = args.openroad
    print("host: {} cores / {} hw threads, governor {}, boost {}".format(
        prov["physical_cores"], prov["hardware_threads"],
        prov["governor"], prov["boost"]))
    print("arms: {} repeats={} threads={} pinned".format(
        args.arms, args.repeats, threads))
    print("results: {}".format(results_dir))

    written = 0
    skipped = 0
    failed = []
    for design in args.designs:
        for stage in args.stages:
            wanted = [
                (a, r)
                for a in args.arms
                for r in range(1, args.repeats + 1)
                if not os.path.exists(
                    result_path(results_dir, design, stage, a + args.arm_suffix, r)
                )
            ]
            if not wanted:
                skipped += len(args.arms) * args.repeats
                continue

            print("\n=== {} {}".format(design, stage))
            try:
                deploy_dir = deploy(DESIGNS[design], stage, args.verbose)
            except SystemExit as exc:
                if not args.keep_going:
                    raise
                print("  deploy failed, skipping: {}".format(exc))
                failed.append((design, stage, "deploy"))
                continue

            for arm, repeat in wanted:
                overrides = ARMS[arm]
                wait_for_no_openroad()
                load = wait_for_idle(args.max_load)
                print("  arm={}{} repeat={} (load {:.2f})".format(
                    arm, args.arm_suffix, repeat, load))
                try:
                    make_wall = run_arm(
                        deploy_dir, stage, threads, overrides, args.openroad,
                        args.verbose,
                    )
                    samples = collect(deploy_dir, stage, threads, overrides)
                except SystemExit as exc:
                    if not args.keep_going:
                        raise
                    print("  arm failed, skipping: {}".format(exc))
                    failed.append((design, stage, arm))
                    break

                record = {
                    "design": design,
                    "target": DESIGNS[design],
                    "stage": stage,
                    "arm": arm + args.arm_suffix,
                    "overrides": overrides,
                    "threads": threads,
                    "pinned": True,
                    "repeat": repeat,
                    "loadavg_at_start": load,
                    "make_wall_s": make_wall,
                    "substeps": samples,
                    "provenance": prov,
                    "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                path = result_path(
                    results_dir, design, stage, arm + args.arm_suffix, repeat
                )
                with open(path, "w") as handle:
                    json.dump(record, handle, indent=2, sort_keys=True)
                written += 1
                for step, got in samples.items():
                    for call in got["repair"]:
                        print("      {:<14} {:<15} setup {}s hold {}s iters {}".format(
                            step, call["kind"], call["setup_s"], call["hold_s"],
                            call["iterations"]))

    print("\nwrote {} arm(s), skipped {} already present".format(written, skipped))
    if failed:
        print("failed: {}".format(failed))
    print("results in {}".format(results_dir))


if __name__ == "__main__":
    main()
