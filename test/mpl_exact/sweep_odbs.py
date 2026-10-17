"""Floorplans at shrinking core sizes, for the DSE regime: most of a
design-space exploration's points are tight or cannot be placed at all.

For each design and scale s (core side times s, area times s^2), run the
lane's floorplan with CORE_AREA scaled, or CORE_UTILIZATION divided by s^2,
and keep 2_1_floorplan.odb and the log's rtl_macro_placer call. Untimed.

usage: sweep_odbs.py --out DIR --jobs N --scales 1,0.9,... <design>...
       <design> is <platform>/<design>/<top>, as in flows.txt.
"""

import argparse
import concurrent.futures
import glob
import os
import re
import shutil
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def settings(tree):
    text = open(os.path.join(tree, "_main", "config.mk")).read()
    env = {}
    for key in ("CORE_AREA", "CORE_UTILIZATION"):
        m = re.search(rf"^export {key}\s*\??=\s*(.+)$", text, re.M)
        if m:
            env[key] = m.group(1).strip()
    return env


def run(design, scales, out, openroad):
    platform, name, top = design.split("/")
    tree = os.path.join(ROOT, f"tmp/@orfs//flow/designs/{platform}/{name}/{top}")
    base = settings(tree)
    lines = []
    for scale in scales:
        env = dict(os.environ, OPENROAD_EXE=openroad)
        if "CORE_AREA" in base:
            x0, y0, x1, y1 = map(float, base["CORE_AREA"].split())
            env["CORE_AREA"] = "%.3f %.3f %.3f %.3f" % (
                x0,
                y0,
                x0 + scale * (x1 - x0),
                y0 + scale * (y1 - y0),
            )
        elif "CORE_UTILIZATION" in base:
            env["CORE_UTILIZATION"] = "%.2f" % (
                float(base["CORE_UTILIZATION"]) / scale**2
            )
        else:
            lines.append(f"{design} {scale} no core setting")
            continue
        dest = os.path.join(out, f"{platform}_{name}", f"{scale:.2f}")
        os.makedirs(dest, exist_ok=True)
        log = os.path.join(dest, "floorplan.log")
        for stale in set(
            glob.glob(f"{tree}/**/results/**/2_1_floorplan.odb", recursive=True)
        ):
            if os.path.exists(stale):
                os.remove(stale)
        with open(log, "w") as f:
            code = subprocess.run(
                [os.path.join(tree, "make"), "do-floorplan"],
                env=env,
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=3600,
            ).returncode
        odbs = glob.glob(f"{tree}/**/results/**/2_1_floorplan.odb", recursive=True)
        if odbs:
            shutil.copy(odbs[0], os.path.join(dest, "2_1_floorplan.odb"))
        mpl = sorted(set(re.findall(r"MPL-0\d+", open(log).read())))
        lines.append(
            f"{design} scale={scale} exit={code} "
            f"{'2_1 ok' if odbs else 'no 2_1'} {' '.join(mpl)}"
        )
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--scales", default="1,0.95,0.9,0.85,0.8,0.7,0.6")
    parser.add_argument("--openroad", required=True)
    parser.add_argument("designs", nargs="+")
    args = parser.parse_args()
    scales = [float(s) for s in args.scales.split(",")]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        for lines in pool.map(
            lambda d: run(d, scales, args.out, args.openroad), args.designs
        ):
            for line in lines:
                print(line, flush=True)


if __name__ == "__main__":
    main()
