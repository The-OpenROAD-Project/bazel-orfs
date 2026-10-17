"""mpl's time to an answer, placed or refused, across the core sweep.

For each <design>/<scale>/2_1_floorplan.odb under --odbs, run every arm's
mpl_bench once, pinned, on an idle machine, with the design's own
rtl_macro_placer settings from its baseline floorplan log. One CSV row per
run, appended: a campaign resumes where it stopped.

usage: bench_sweep.py --odbs DIR --dumps DIR --out results.csv
                      --arm base=B --arm fallback=F --arm first=X
"""

import argparse
import csv
import glob
import os
import re
import subprocess

from bench import mpl_args, wait_idle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--odbs", required=True)
    parser.add_argument("--dumps", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--arm", action="append", required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--max-load", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    arms = [a.split("=", 1) for a in args.arm]
    done = set()
    if os.path.exists(args.out):
        for r in csv.DictReader(open(args.out)):
            done.add((r["design"], r["scale"], r["arm"]))
    new_file = not os.path.exists(args.out)
    out = open(args.out, "a", newline="")
    writer = csv.writer(out)
    if new_file:
        writer.writerow(
            [
                "design",
                "scale",
                "arm",
                "loadavg_at_start",
                "seconds",
                "placed",
                "macro_net_hpwl_um",
                "error",
                "proof",
            ]
        )
    for odb in sorted(
        glob.glob(os.path.join(args.odbs, "*", "*", "2_1_floorplan.odb"))
    ):
        scale = os.path.basename(os.path.dirname(odb))
        design = os.path.basename(os.path.dirname(os.path.dirname(odb)))
        log = os.path.join(args.dumps, design, "floorplan.log")
        extra = mpl_args(log) if os.path.exists(log) else None
        if extra is None:
            continue
        for arm, binary in arms:
            if (design, scale, arm) in done:
                continue
            load = wait_idle(args.max_load)
            cmd = [
                "taskset",
                "-c",
                f"0-{args.threads - 1}",
                binary,
                odb,
                "--threads",
                str(args.threads),
            ] + extra
            try:
                run = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                    cwd=os.path.dirname(args.out),
                )
                stdout, stderr = run.stdout, run.stderr
            except subprocess.TimeoutExpired:
                stdout, stderr = "", "timeout"
            rows = [l for l in stdout.splitlines() if re.match(r"^\d+,", l)]
            error = ""
            m = re.search(r"\[ERROR (MPL-\d+)\]", stdout + stderr)
            if m:
                error = m.group(1)
            elif stderr == "timeout":
                error = "timeout"
            if rows:
                _, seconds, placed, hpwl = rows[0].split(",")
            else:
                seconds, placed, hpwl = "", "0", ""
            proof = int("(proven)" in stdout + stderr)
            writer.writerow(
                [design, scale, arm, f"{load:.2f}", seconds, placed, hpwl, error, proof]
            )
            out.flush()
            print(design, scale, arm, seconds, placed, error, flush=True)


if __name__ == "__main__":
    main()
