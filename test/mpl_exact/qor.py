"""Both arms through global route, as Bazel builds them, and the numbers.

Arm "base" is a bazel-orfs checkout without the carried mpl patches, arm
"new" the one with them; everything else is identical, so a stage's key
differs only by the OpenROAD binary. One build per design and arm, at
default settings.

  qor.py build --workspace W --arm A --jobs J <flow>...
  qor.py harvest --workspace W --arm A --out results.csv <flow>...

harvest copies each stage's small metric and log files out of Bazel's
output tree by exact path, then reads: mpl's runtime (MPL-0500), the
global route stage's setup worst slack and the clock period, and the
elapsed time of each stage.
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess


def bazel(workspace, *args):
    return subprocess.run(
        ["bazelisk", *args], cwd=workspace, capture_output=True, text=True
    )


def files_of(workspace, target):
    r = bazel(
        workspace,
        "cquery",
        "--output=files",
        "--output_groups=+logs,+reports,+jsons",
        target,
    )
    return [l for l in r.stdout.split("\n") if l.strip()]


def build(args):
    targets = [f + "_grt" for f in args.flows]
    r = subprocess.run(
        ["bazelisk", "build", "--keep_going", f"--jobs={args.jobs}", *targets],
        cwd=args.workspace,
    )
    return r.returncode


def first(pattern, text, cast=float):
    m = re.search(pattern, text)
    return cast(m.group(1)) if m else None


def harvest(args):
    # The metrics JSONs are an output group of their own; building it
    # re-runs nothing that is already built.
    stages = [
        f"{f}_{s}" for f in args.flows for s in ("floorplan", "place", "cts", "grt")
    ]
    subprocess.run(
        [
            "bazelisk",
            "build",
            "--keep_going",
            "--output_groups=+logs,+reports,+jsons",
            *stages,
        ],
        cwd=args.workspace,
        capture_output=True,
    )
    rows = []
    for flow in args.flows:
        name = re.sub(r"@orfs//flow/designs/|:.*", "", flow).replace("/", "_")
        dest = os.path.join(os.path.dirname(args.out), args.arm, name)
        os.makedirs(dest, exist_ok=True)
        row = {"design": name, "arm": args.arm}
        for stage in ("floorplan", "place", "cts", "grt"):
            for path in files_of(args.workspace, f"{flow}_{stage}"):
                base = os.path.basename(path)
                if not (base.endswith(".json") or base.endswith(".log")):
                    continue
                src = os.path.join(args.workspace, path)
                if os.path.isfile(src) and os.path.getsize(src) <= 8 * 1024 * 1024:
                    target = os.path.join(dest, base)
                    if os.path.exists(target):
                        os.remove(target)  # copies of Bazel outputs are read-only
                    shutil.copy(src, target)
        macro_log = os.path.join(dest, "2_2_floorplan_macro.log")
        if os.path.exists(macro_log):
            row["mpl_seconds"] = first(
                r"MPL-0500\] Runtime: ([\d.]+)s", open(macro_log).read()
            )
        grt = os.path.join(dest, "5_1_grt.json")
        if os.path.exists(grt):
            metrics = json.load(open(grt))
            for key, value in metrics.items():
                if re.search(
                    r"timing__setup__ws$|timing__setup__tns$|"
                    r"clock__period|route__wirelength$",
                    key,
                ):
                    row[key] = value
        for stage_json in sorted(f for f in os.listdir(dest) if f.endswith(".json")):
            metrics = json.load(open(os.path.join(dest, stage_json)))
            for key, value in metrics.items():
                if key.endswith("__runtime__total"):
                    row[key] = value
        rows.append(row)
    keys = sorted({k for r in rows for k in r} - {"design", "arm"})
    new = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as f:
        w = csv.DictWriter(f, ["design", "arm"] + keys, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "harvest"])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--out")
    parser.add_argument("flows", nargs="+")
    args = parser.parse_args()
    if args.command == "build":
        raise SystemExit(build(args))
    harvest(args)


if __name__ == "__main__":
    main()
