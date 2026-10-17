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


def unit_peak(entry, stage=None):
    """A unit's footprint in GB: its largest stage, or `stage` alone when the
    record has it (a lane runs one stage), padded if estimated."""
    stages = entry["stages"]
    if stage in stages:
        peak = stages[stage]["peak_gb"]
    else:
        peak = max(s["peak_gb"] for s in stages.values())
    return peak * ESTIMATE_PAD if entry.get("source") != "measured" else peak


def unit_minutes(entry, stage=None):
    """A unit's time: its stages one after another, or `stage` alone when
    the record has it (a lane runs one stage)."""
    stages = entry["stages"]
    if stage in stages:
        return stages[stage].get("minutes", 0)
    return sum(s.get("minutes", 0) for s in stages.values())


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


def meminfo_gb(key, meminfo="/proc/meminfo"):
    """A /proc/meminfo field in GB, e.g. "MemAvailable" or "SwapFree"."""
    with open(meminfo) as f:
        for line in f:
            if line.startswith(key + ":"):
                return int(line.split()[1]) / 1024 / 1024
    raise SystemExit(f"schedule: no {key} in {meminfo}")


def mem_available_gb(meminfo="/proc/meminfo"):
    return meminfo_gb("MemAvailable", meminfo)


OOMD_SOCKET = "/run/systemd/oom/io.systemd.ManagedOOM"
UNIT_DIRS = ("/etc/systemd/system", "/run/systemd/system", "/usr/lib/systemd/system")
KILL = re.compile(r"^\s*(ManagedOOM(?:MemoryPressure|Swap))\s*=\s*kill\b", re.M)


def oomd_killer(cgroup="/proc/self/cgroup", socket=OOMD_SOCKET, unit_dirs=UNIT_DIRS):
    """What would kill this process for using swap, or None.

    systemd-oomd kills a whole cgroup under a unit set to
    ManagedOOMMemoryPressure=kill once memory pressure stays over its limit
    (Ubuntu ships user@.service at 50 % for 20 s), and paging is exactly
    that pressure. Read from files only: oomctl talks to oomd's socket,
    which starts oomd when it was stopped. None when oomd's socket is gone,
    that is when oomd and its socket are stopped."""
    if not os.path.exists(socket):
        return None
    try:
        with open(cgroup) as f:
            path = f.read().strip().split("::", 1)[-1]
    except OSError:
        return None
    for unit in path.strip("/").split("/"):
        template = re.sub(r"@[^.]*\.", "@.", unit)
        names = [unit] if template == unit else [unit, template]
        for d in unit_dirs:
            for name in names:
                files = [os.path.join(d, name)]
                dropins = os.path.join(d, name + ".d")
                if os.path.isdir(dropins):
                    files += [
                        os.path.join(dropins, c)
                        for c in sorted(os.listdir(dropins))
                        if c.endswith(".conf")
                    ]
                for f in files:
                    if not os.path.isfile(f):
                        continue
                    with open(f, errors="replace") as fh:
                        m = KILL.search(fh.read())
                    if m:
                        return f"systemd-oomd: {m.group(1)}=kill on {unit} ({f})"
    return None


def preflight(waves, peaks, ram_free, swap_free, margin, killer):
    """Why the plan cannot run on this machine; empty when it can.

    A wave whose summed peak does not fit free RAM and swap is killed by
    the kernel, however it is packed: a unit over the budget runs alone and
    no budget makes it smaller. A wave that pages, under a systemd-oomd
    that kills on memory pressure, is killed by oomd, and it takes the
    other processes of the cgroup, such as the session that started it,
    with it."""
    refusals = []
    for i, (_, wave) in enumerate(waves, 1):
        total = sum(peaks[u] for u in wave)
        if total > ram_free + swap_free - margin:
            refusals.append(
                f"wave {i} ({', '.join(wave)}) peaks at {total:.0f} GB: more than "
                f"free RAM and swap ({ram_free:.0f} + {swap_free:.0f} GB) less the "
                f"{margin:.0f} GB margin. Add swap, or build it on a larger machine."
            )
        elif killer and total > ram_free - margin:
            refusals.append(
                f"wave {i} ({', '.join(wave)}) peaks at {total:.0f} GB, more than "
                f"free RAM ({ram_free:.0f} GB) less the margin, so it pages, and "
                f"{killer} kills it. Stop oomd for the build: sudo systemctl stop "
                "systemd-oomd.socket systemd-oomd.service (start them after)."
            )
    return refusals


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


def lane_tree(lane_dir, unit):
    """A unit's deps-lane tree, relative to the workspace."""
    return os.path.join(lane_dir, unit)


def lane_start(deps, package, unit, stage, tree, bazel_args):
    """The command that installs `unit`'s `stage` in its own lane tree:
    Bazel builds what the stage needs and copies it in (deps-lane skill)."""
    return (
        ["bazelisk", "run"]
        + bazel_args
        + [deps, "--", "start", "//%s:%s" % (package, unit), stage]
        + ["--dir", tree, "--fresh"]
    )


def run(waves, macros, parents, build):
    """Build the waves in order: {wave number: exit code}, a skipped wave absent.

    A failed macro wave does not stop the other macro waves, which do not
    read each other; it stops the parents, which read every macro."""
    results = {}
    for i, (kind, wave) in enumerate(waves, 1):
        if kind == "parent" and any(results.values()):
            continue
        targets = [t for u in wave for t in (macros.get(u) or parents.get(u))]
        results[i] = build(i, wave, targets)
    return results


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
    ap.add_argument(
        "--lane",
        metavar="STAGE",
        help="run STAGE of each unit in its own deps-lane tree instead of a "
        "bazelisk build; units of a wave run side by side",
    )
    ap.add_argument(
        "--lane-dir", default="tmp/schedule", help="where the lane trees go"
    )
    ap.add_argument(
        "--deps", default="@bazel-orfs//:deps", help="bazel-orfs's deps target"
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
    swap = meminfo_gb("SwapFree")
    budget = args.budget if args.budget is not None else free - args.margin
    stage = args.lane
    peaks = {u: unit_peak(units[u], stage) for u in macros}
    waves = [("macros", w) for w in pack(peaks, budget)]
    waves += [("parent", [p]) for p in parents]
    refusals = preflight(
        waves,
        {u: unit_peak(units[u], stage) for u in list(macros) + list(parents)},
        free,
        swap,
        args.margin,
        oomd_killer(),
    )
    print(
        f"budget {budget:.0f} GB ({free:.0f} free, {swap:.0f} swap free, "
        f"{args.margin:.0f} margin)"
        + (f"; lane mode, stage {stage}, trees in {args.lane_dir}" if stage else "")
    )
    for i, (kind, wave) in enumerate(waves, 1):
        sizes = ", ".join(
            f"{u} ({unit_peak(units[u], stage):.0f}"
            + ("" if units[u].get("source") == "measured" else ", estimated")
            + ")"
            for u in wave
        )
        total = sum(unit_peak(units[u], stage) for u in wave)
        minutes = max(unit_minutes(units[u], stage) for u in wave)
        note = "  OVER BUDGET: runs alone" if total > budget else ""
        print(
            f"wave {i} ({kind}): {sizes}  peak {total:.0f} GB, ~{minutes:.0f} min{note}"
        )
    if refusals:
        for r in refusals:
            print(f"schedule: refused: {r}", file=sys.stderr)
        return 2
    if args.plan_only:
        return 0

    bin_dir = None if stage else bazel_bin(workspace)
    changed = []

    def build(i, wave, targets):
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
            print(f"wave {i} failed ({rc})", file=sys.stderr)
        return rc

    def lane(i, wave, targets):
        trees = {}
        for u in wave:
            tree = lane_tree(args.lane_dir, u)
            cmd = lane_start(args.deps, args.package, u, stage, tree, args.bazel_arg)
            print(f"wave {i}: {' '.join(cmd)}", flush=True)
            rc = subprocess.call(cmd, cwd=workspace)
            if rc:
                print(f"wave {i}: {u}'s lane did not start ({rc})", file=sys.stderr)
                return rc
            trees[u] = os.path.join(workspace, tree)
        procs = {}
        for u, tree in trees.items():
            log = open(os.path.join(tree, "schedule.log"), "w")
            print(f"wave {i}: {tree}/make do-{stage} > {log.name}", flush=True)
            procs[u] = (
                subprocess.Popen(
                    [os.path.join(tree, "make"), "do-" + stage],
                    cwd=workspace,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                ),
                log,
            )
        rcs = {}
        for u, (p, log) in procs.items():
            rcs[u] = p.wait()
            log.close()
            d = log_dir(os.path.join(trees[u], "_main"), args.package, u, args.variant)
            entry, did = refresh(units.get(u), measure(d) if d else {}, rcs[u] == 0)
            if did:
                units[u] = entry
                changed.append(u)
            if rcs[u]:
                print(f"wave {i}: {u} failed ({rcs[u]})", file=sys.stderr)
        return max(rcs.values(), default=0)

    results = run(waves, macros, parents, lane if stage else build)
    for i, (kind, wave) in enumerate(waves, 1):
        if i not in results:
            print(
                f"wave {i} ({kind}) not run: a macro wave failed, and a parent reads every macro",
                file=sys.stderr,
            )
    rc = max(results.values(), default=0)
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
