"""mpl runtime and macro-net wirelength, base vs new, on an idle machine.

For every design with a deployed floorplan lane: read the flow's own
rtl_macro_placer settings from its floorplan log, then run mpl_bench of
each arm `--repeats` times on the lane's 2_1_floorplan.odb, pinned to the
first `--threads` cores. A run starts only while the 1-minute load average
is below `--max-load`; the load at start is recorded. One CSV row per run.

usage: bench.py --base B --new N --dumps DIR --out results.csv [--repeats 3]
"""

import argparse
import csv
import glob
import os
import re
import subprocess
import time

TREE = "tmp/@orfs//flow/designs/{platform}/{design}/{top}"


def flows():
    here = os.path.dirname(os.path.abspath(__file__))
    for line in open(os.path.join(here, "flows.txt")):
        flow = line.strip()
        m = re.match(r"@orfs//flow/designs/([^/]+)/([^:]+):(.+)", flow)
        yield m.group(1), m.group(2), m.group(3)


def mpl_args(log):
    """The flow's rtl_macro_placer call, as mpl_bench arguments."""
    for line in open(log, errors="replace"):
        if line.startswith("rtl_macro_placer "):
            args = []
            m = re.search(r'-min_channel_size "?([\d.]+) ([\d.]+)"?', line)
            if m:
                args += ["--channel", m.group(1), m.group(2)]
            if "-pin_aware_channels" in line:
                args.append("--pin-aware")
            m = re.search(r"-target_util ([\d.]+)", line)
            if m:
                args += ["--target-util", m.group(1)]
            m = re.search(r"-max_num_level (\d+)", line)
            if m:
                args += ["--max-num-level", m.group(1)]
            return args
    return None


def wait_idle(max_load):
    while os.getloadavg()[0] >= max_load:
        time.sleep(30)
    return os.getloadavg()[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--dumps", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--max-load", type=float, default=2.0)
    args = parser.parse_args()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    done = set()
    if os.path.exists(args.out):
        for r in csv.DictReader(open(args.out)):
            done.add((r["design"], r["arm"], r["repeat"]))
    new_file = not os.path.exists(args.out)
    out = open(args.out, "a", newline="")
    writer = csv.writer(out)
    if new_file:
        writer.writerow(
            [
                "design",
                "arm",
                "repeat",
                "loadavg_at_start",
                "seconds",
                "placed",
                "macro_net_hpwl_um",
            ]
        )
    for platform, design, top in flows():
        name = f"{platform}_{design}"
        log = os.path.join(args.dumps, name, "floorplan.log")
        tree = os.path.join(
            root, TREE.format(platform=platform, design=design, top=top)
        )
        odbs = glob.glob(f"{tree}/**/results/**/2_1_floorplan.odb", recursive=True)
        if not os.path.exists(log) or not odbs:
            print(f"SKIP {name}: no lane or log")
            continue
        extra = mpl_args(log)
        if extra is None:
            print(f"SKIP {name}: no rtl_macro_placer call")
            continue
        for repeat in range(args.repeats):
            for arm, binary in (("base", args.base), ("new", args.new)):
                if (name, arm, str(repeat)) in done:
                    continue
                load = wait_idle(args.max_load)
                cmd = [
                    "taskset",
                    "-c",
                    f"0-{args.threads - 1}",
                    binary,
                    odbs[0],
                    "--threads",
                    str(args.threads),
                ] + extra
                run = subprocess.run(
                    cmd, capture_output=True, text=True, cwd=os.path.dirname(args.out)
                )
                rows = [l for l in run.stdout.splitlines() if re.match(r"^\d+,", l)]
                if run.returncode != 0 or not rows:
                    print(f"FAIL {name} {arm} {repeat}: exit {run.returncode}")
                    writer.writerow([name, arm, repeat, f"{load:.2f}", "", 0, ""])
                    continue
                _, seconds, placed, hpwl = rows[0].split(",")
                writer.writerow(
                    [name, arm, repeat, f"{load:.2f}", seconds, placed, hpwl]
                )
                out.flush()
                print(
                    f"{name} {arm} {repeat} {seconds}s placed={placed} " f"hpwl={hpwl}"
                )


if __name__ == "__main__":
    main()
