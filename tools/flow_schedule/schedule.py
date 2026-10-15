"""A scheduler at home: build a design's flows in waves that fit memory.

Run through an orfs_schedule() target (docs/schedule.md):

    bazelisk run //<pkg>:build [-- --plan-only] [--budget GB] [--units A,B]

Reads resources.json beside the target's BUILD file, packs the macro
units into waves whose summed peak memory fits the budget, runs one
`bazelisk build` per wave, the parent units alone and last, and then
reads each unit's ORFS stage logs to record what it measured.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# a missing record is the AI's to write, from a quick assessment
NO_RECORD = (
    "no resources.json for this schedule ({path}). The first one comes from "
    "an assessment, not a measuring build: follow the scale-to-memory skill "
    "(.claude/skills/scale-to-memory), or docs/schedule.md, 'Managed by AI skills'."
)

# an estimate is padded; a measurement is not
ESTIMATE_PAD = 1.2
# a measured peak or time this far off the record is rewritten
REFRESH = 0.2

STAGES = {
    "1": "synth",
    "2": "floorplan",
    "3": "place",
    "4": "cts",
    "5": "grt",
    "6": "route",
    "7": "final",
}

ELAPSED = re.compile(r"Elapsed time: (?:(\d+):)?(\d+):([\d.]+)\[h:\]min:sec")
PEAK = re.compile(r"Peak memory: (\d+)KB")


def parse_units(specs):
    """'Name=//a:b,//a:c' -> {'Name': ['//a:b', '//a:c']}, in order."""
    units = {}
    for spec in specs or []:
        name, _, targets = spec.partition("=")
        if not name or not targets:
            raise SystemExit(f"schedule: bad unit {spec!r}, want Name=//pkg:target,...")
        units[name] = targets.split(",")
    return units


def unit_peak(entry):
    """A unit's footprint in GB: its largest stage, padded if estimated."""
    peak = max(s["peak_gb"] for s in entry["stages"].values())
    return peak * ESTIMATE_PAD if entry.get("source") != "measured" else peak


def unit_minutes(entry):
    return sum(s.get("minutes", 0) for s in entry["stages"].values())


def pack(peaks, budget):
    """Macro units into waves whose summed peak fits `budget`, largest first.

    A unit larger than the budget gets a wave of its own: it cannot be
    split, and running it alone is the best the machine can do."""
    waves = []
    for name in sorted(peaks, key=lambda n: (-peaks[n], n)):
        for wave in waves:
            if sum(peaks[n] for n in wave) + peaks[name] <= budget:
                wave.append(name)
                break
        else:
            waves.append([name])
    return waves


def mem_available_gb(meminfo="/proc/meminfo"):
    with open(meminfo) as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024 / 1024
    raise SystemExit("schedule: no MemAvailable in " + meminfo)


def parse_log(text):
    """(peak GB, minutes) from an ORFS step log's last Elapsed line, or None."""
    found = None
    for line in text.splitlines():
        e, p = ELAPSED.search(line), PEAK.search(line)
        if e and p:
            h, m, s = e.groups()
            minutes = int(h or 0) * 60 + int(m) + float(s) / 60
            found = (int(p.group(1)) / 1024 / 1024, minutes)
    return found


def measure(log_dir):
    """{stage: {peak_gb, minutes}} from the step logs in one flow's log dir.

    Reads only the files directly in `log_dir`: never a recursive walk of
    bazel's output tree."""
    stages = {}
    if not os.path.isdir(log_dir):
        return stages
    for f in sorted(os.listdir(log_dir)):
        stage = STAGES.get(f[:1])
        if not stage or not f.endswith(".log"):
            continue
        with open(os.path.join(log_dir, f), errors="replace") as fh:
            got = parse_log(fh.read())
        if not got:
            continue
        s = stages.setdefault(stage, {"peak_gb": 0.0, "minutes": 0.0})
        s["peak_gb"] = max(s["peak_gb"], round(got[0], 1))
        s["minutes"] = round(s["minutes"] + got[1], 1)
    return stages


def refresh(entry, measured, complete=True):
    """The entry to record for a unit after a run, and whether it changed.

    Measured stages are merged into the entry: a stage that did not run
    keeps what was recorded, so a failed or interrupted wave never shrinks
    a unit to the stages it reached. The unit becomes `measured` only when
    its wave completed."""
    if not measured:
        return entry, False
    old = entry or {"source": "estimated", "stages": {}}
    stages = dict(old.get("stages", {}))
    moved = False
    for stage, now in measured.items():
        was = stages.get(stage)
        if (
            was is None
            or old.get("source") != "measured"
            or any(
                was.get(k) and abs(now[k] - was[k]) > REFRESH * was[k]
                for k in ("peak_gb", "minutes")
            )
        ):
            moved = moved or was != now
            stages[stage] = now
    source = "measured" if complete else old.get("source", "estimated")
    if not moved and source == old.get("source"):
        return old, False
    new = dict(old, source=source, stages=stages)
    if source == "measured":
        new.pop("basis", None)
    return new, True


def bazel_bin(workspace):
    return subprocess.check_output(
        ["bazelisk", "info", "bazel-bin"], cwd=workspace, text=True
    ).strip()


def log_dir(bin_dir, package, unit, variant):
    """logs/<platform>/<unit>/<variant> under the package; listdir, no glob."""
    logs = os.path.join(bin_dir, package, "logs")
    if not os.path.isdir(logs):
        return None
    for platform in sorted(os.listdir(logs)):
        d = os.path.join(logs, platform, unit, variant)
        if os.path.isdir(d):
            return d
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--package", required=True)
    ap.add_argument("--resources", required=True)
    ap.add_argument("--macro", action="append", help="Name=//pkg:t,...")
    ap.add_argument("--parent", action="append", help="Name=//pkg:t,...")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument(
        "--budget", type=float, help="GB; default free memory less --margin"
    )
    ap.add_argument("--margin", type=float, default=5.0, help="GB kept free")
    ap.add_argument("--units", help="build only these units, comma separated")
    ap.add_argument("--variant", default="base")
    ap.add_argument(
        "--bazel-arg", action="append", default=[], help="passed to every build"
    )
    args = ap.parse_args(argv)

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace:
        raise SystemExit("schedule: run it with `bazelisk run`")
    macros, parents = parse_units(args.macro), parse_units(args.parent)
    if args.units:
        keep = set(args.units.split(","))
        unknown = keep - set(macros) - set(parents)
        if unknown:
            raise SystemExit(f"schedule: no such units: {sorted(unknown)}")
        macros = {k: v for k, v in macros.items() if k in keep}
        parents = {k: v for k, v in parents.items() if k in keep}

    path = os.path.join(workspace, args.package, args.resources)
    if not os.path.exists(path):
        raise SystemExit(NO_RECORD.format(path=path))
    with open(path) as f:
        record = json.load(f)
    units = record.setdefault("units", {})
    missing = [u for u in list(macros) + list(parents) if u not in units]
    if missing:
        raise SystemExit(
            f"schedule: {path} has no entry for {missing}; "
            + NO_RECORD.format(path=path)
        )

    free = mem_available_gb()
    budget = args.budget if args.budget is not None else free - args.margin
    if budget > free - args.margin:
        print(
            f"warning: budget {budget:.0f} GB is above free memory less the margin "
            f"({free - args.margin:.0f} GB): a full wave will page or be killed",
            file=sys.stderr,
        )
    peaks = {u: unit_peak(units[u]) for u in macros}
    waves = [("macros", w) for w in pack(peaks, budget)]
    waves += [("parent", [p]) for p in parents]
    print(f"budget {budget:.0f} GB ({free:.0f} free, {args.margin:.0f} margin)")
    for i, (kind, wave) in enumerate(waves, 1):
        sizes = ", ".join(
            f"{u} ({unit_peak(units[u]):.0f}"
            + ("" if units[u].get("source") == "measured" else ", estimated")
            + ")"
            for u in wave
        )
        total = sum(unit_peak(units[u]) for u in wave)
        minutes = max(unit_minutes(units[u]) for u in wave)
        note = "  OVER BUDGET: runs alone" if total > budget else ""
        print(
            f"wave {i} ({kind}): {sizes}  peak {total:.0f} GB, ~{minutes:.0f} min{note}"
        )
    if args.plan_only:
        return 0

    bin_dir = bazel_bin(workspace)
    changed = []
    rc = 0
    for i, (kind, wave) in enumerate(waves, 1):
        targets = [t for u in wave for t in (macros.get(u) or parents.get(u))]
        print(f"wave {i}: bazelisk build {' '.join(targets)}", flush=True)
        rc = subprocess.call(
            ["bazelisk", "build"] + args.bazel_arg + targets, cwd=workspace
        )
        for u in wave:
            d = log_dir(bin_dir, args.package, u, args.variant)
            entry, did = refresh(units.get(u), measure(d) if d else {}, rc == 0)
            if did:
                units[u] = entry
                changed.append(u)
        if rc:
            print(f"wave {i} failed ({rc}); later waves not run", file=sys.stderr)
            break
    if changed:
        with open(path, "w") as f:
            json.dump(record, f, indent=2, sort_keys=True)
            f.write("\n")
        print(
            f"resources.json updated for {changed}: commit it when it is "
            "materially out of date"
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
