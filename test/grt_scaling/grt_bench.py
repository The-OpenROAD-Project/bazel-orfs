#!/usr/bin/env python3
"""Run a matrix of global-route arms, unattended, one JSON per arm.

    grt_bench.py matrix.json results_dir/

matrix.json:

    {
      "designs": {
        "xs":  {"deps": "tmp/xs_grt_lab/deps", "odb": "results/asap7/XSCore/base/4_cts.odb"},
        "wb2": {"deps": "tmp/wb_2000",         "odb": "test/grt_scaling/results/asap7/wirebound/d2000_g32/4_cts.odb"}
      },
      "arms": {
        "baseline":  {},
        "iter5":     {"args": "-congestion_iterations 5 -allow_congestion"},
        "batched48": {"args": "-snapshot_batched_width 48"},
        "cugr":      {"args": "-use_cugr"},
        "m2m5":      {"layers": "M2 M5"},
        "hugepages": {"env": {"GLIBC_TUNABLES": "glibc.malloc.hugetlb=1"}},
        "byo":       {"openroad": "/abs/path/to/openroad"}
      },
      "args": "-congestion_iterations 3 -allow_congestion",
      "timeout_s": 9000,
      "memory_max": "60G",
      "swap_max": "70G",
      "perf": true,
      "repeats": 1
    }

Each (design, arm, repeat) runs `./make run RUN_SCRIPT=grt_bench.tcl` in the
design's deps tree, serially, inside its own systemd scope with a memory
cap and a wall-clock timeout; a memory sampler writes the router's RSS and
swap every 5 s next to the result. A run that is killed still leaves the
JSON of the steps grt_bench.tcl finished, and the driver records how it
ended (ok, timeout, oom, error). Done cells are skipped, so the matrix is
resumable. Nothing here asks a question.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH_TCL = os.path.join(HERE, "grt_bench.tcl")


def cell_name(design, arm, rep):
    return "%s__%s__r%d" % (design, arm, rep)


def load_matrix(path):
    with open(path) as f:
        m = json.load(f)
    m.setdefault("args", "")
    m.setdefault("timeout_s", 9000)
    m.setdefault("memory_max", None)
    m.setdefault("swap_max", None)
    m.setdefault("perf", False)
    m.setdefault("repeats", 1)
    m.setdefault("arms", {"baseline": {}})
    return m


def make_command(design, arm, out_json, matrix):
    """The `./make run ...` argv for one cell, absolute paths throughout."""
    deps = os.path.abspath(design["deps"])
    odb = (
        os.path.join(deps, "_main", design["odb"])
        if not os.path.isabs(design["odb"])
        else design["odb"]
    )
    log_dir = os.path.dirname(out_json)
    argv = [
        os.path.join(deps, "make"),
        "run",
        "RUN_SCRIPT=" + BENCH_TCL,
        "ODB_FILE=" + odb,
        "GRT_BENCH_OUT=" + out_json,
        "LOG_DIR=" + log_dir,
        "RUN_LOG_NAME_STEM=" + os.path.splitext(os.path.basename(out_json))[0],
    ]
    # Matrix-wide arguments first (the iteration budget every arm shares on
    # a small arm), then the arm's own.
    args = (matrix.get("args", "") + " " + arm.get("args", "")).strip()
    if args:
        argv.append("GRT_BENCH_ARGS=" + args)
    if arm.get("layers"):
        argv.append("GRT_BENCH_LAYERS=" + arm["layers"])
    if arm.get("pin_access") is False:
        argv.append("GRT_BENCH_PIN_ACCESS=0")
    if arm.get("openroad"):
        argv.append("OPENROAD_EXE=" + os.path.abspath(arm["openroad"]))
    if arm.get("threads"):
        argv.append("NUM_CORES=%d" % int(arm["threads"]))
    return argv


def scope_command(argv, unit, matrix):
    """Wrap in a transient systemd scope with the matrix's memory caps."""
    if not shutil.which("systemd-run"):
        return argv
    cmd = ["systemd-run", "--user", "--scope", "--unit=" + unit, "-q"]
    if matrix.get("memory_max"):
        cmd.append("-p")
        cmd.append("MemoryMax=" + matrix["memory_max"])
    if matrix.get("swap_max"):
        cmd.append("-p")
        cmd.append("MemorySwapMax=" + matrix["swap_max"])
    return cmd + argv


def openroad_pid(children_of):
    """The openroad process under a shell, found by comm."""
    try:
        out = subprocess.run(
            ["pgrep", "-P", str(children_of)], capture_output=True, text=True
        ).stdout
    except OSError:
        return None
    for pid in out.split():
        try:
            with open("/proc/%s/comm" % pid) as f:
                if f.read().strip() == "openroad":
                    return int(pid)
        except OSError:
            continue
        found = openroad_pid(int(pid))
        if found:
            return found
    return None


def sample_memory(pid):
    vals = {}
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                for key in ("VmRSS", "VmSwap", "VmHWM"):
                    if line.startswith(key + ":"):
                        vals[key] = int(line.split()[1])
    except OSError:
        return None
    return vals


def run_cell(design_name, design, arm_name, arm, rep, results_dir, matrix):
    name = cell_name(design_name, arm_name, rep)
    out_json = os.path.abspath(os.path.join(results_dir, name + ".json"))
    status_path = out_json + ".status"
    if os.path.exists(status_path):
        with open(status_path) as f:
            print("skip %s: %s" % (name, f.read().strip()))
        return
    argv = make_command(design, arm, out_json, matrix)
    env = dict(os.environ)
    env.update(arm.get("env", {}))
    if matrix.get("perf"):
        perf_data = out_json + ".perf.data"
        argv = ["perf", "record", "-q", "-F", "199", "-o", perf_data, "--"] + argv
    cmd = scope_command(argv, "grt-bench-" + name, matrix)
    print("run  %s: %s" % (name, " ".join(cmd[-6:])))
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=open(out_json + ".driver.log", "w"),
        stderr=subprocess.STDOUT,
    )
    mem_log = open(out_json + ".mem.csv", "w")
    mem_log.write("t_s,vm_rss_kb,vm_swap_kb,vm_hwm_kb\n")
    pid = None
    status = "ok"
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        if time.time() - t0 > matrix["timeout_s"]:
            status = "timeout"
            subprocess.run(
                ["systemctl", "--user", "stop", "grt-bench-" + name + ".scope"],
                capture_output=True,
            )
            proc.wait()
            break
        if pid is None:
            pid = openroad_pid(proc.pid)
        if pid is not None:
            s = sample_memory(pid)
            if s:
                mem_log.write(
                    "%.0f,%d,%d,%d\n"
                    % (
                        time.time() - t0,
                        s.get("VmRSS", 0),
                        s.get("VmSwap", 0),
                        s.get("VmHWM", 0),
                    )
                )
                mem_log.flush()
        time.sleep(5)
    mem_log.close()
    if status == "ok" and proc.returncode != 0:
        status = (
            "oom" if proc.returncode in (137, -9) else "error(%d)" % proc.returncode
        )
    if matrix.get("perf") and os.path.exists(out_json + ".perf.data"):
        with open(out_json + ".perf.txt", "w") as f:
            subprocess.run(
                [
                    "perf",
                    "report",
                    "-i",
                    out_json + ".perf.data",
                    "--stdio",
                    "--sort=sym",
                ],
                stdout=f,
                stderr=subprocess.DEVNULL,
            )
    summary = {
        "status": status,
        "wall_s": round(time.time() - t0, 1),
        "design": design_name,
        "arm": arm_name,
        "repeat": rep,
    }
    # FastRoute's phase timers and the router's wirelength are logger
    # metrics; the session writes them to <out>.metrics.json at exit, after
    # grt_bench.tcl's own fold, so merge them here.
    metrics_path = os.path.splitext(out_json)[0] + ".metrics.json"
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path) as f:
                for key, value in json.load(f).items():
                    if key.startswith("global_route__"):
                        summary[key[len("global_route__") :]] = value
        except ValueError:
            summary["metrics_json_error"] = True
    if os.path.exists(out_json):
        try:
            with open(out_json) as f:
                summary.update(json.load(f))
        except ValueError:
            summary["json_error"] = True
        with open(out_json, "w") as f:
            json.dump(summary, f, indent=1, sort_keys=True)
    else:
        with open(out_json, "w") as f:
            json.dump(summary, f, indent=1, sort_keys=True)
    with open(status_path, "w") as f:
        f.write(status + "\n")
    print("done %s: %s in %.0f s" % (name, status, summary["wall_s"]))


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("matrix")
    ap.add_argument("results_dir")
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="design or arm name to run; repeatable",
    )
    a = ap.parse_args(argv[1:])
    matrix = load_matrix(a.matrix)
    os.makedirs(a.results_dir, exist_ok=True)
    for design_name, design in matrix["designs"].items():
        if (
            a.only
            and design_name not in a.only
            and not any(x in matrix["arms"] for x in a.only)
        ):
            continue
        for arm_name, arm in matrix["arms"].items():
            if a.only and arm_name not in a.only and design_name not in a.only:
                continue
            for rep in range(int(matrix["repeats"])):
                run_cell(design_name, design, arm_name, arm, rep, a.results_dir, matrix)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
