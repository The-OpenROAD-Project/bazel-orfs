"""Does carrying #11395 change a place stage that does not use its command?

The PR says "no existing behavior changes". It also deletes the two hunks
in `Replace::doIncrementalPlace` that forced uniform target density, and
its own diff adds `-density uniform` to three calls in
src/odb/test/replace_hier_mod1.tcl -- which is that behavior change
showing up in a golden test.

ORFS reaches that code from exactly one place: `resize.tcl` runs
`global_placement -incremental` when SWAP_ARITH_OPERATORS is set. Among
the asap7 designs that is mock-alu, riscv32i and ibex; for every other
design the hunk is unreachable and an A/B of it would measure nothing.
So this compares the designs that take the path against one that does
not, and does it on the stock design targets -- no probe, no rung, the
flow as shipped.

    python3 test/estimate_density/ab_incremental.py --arm baseline
    python3 test/estimate_density/ab_incremental.py --arm patched
    python3 test/estimate_density/ab_incremental.py --compare

The arm is selected by commenting the `patches` attribute out of
MODULE.bazel and back in, which is what makes both arms real binaries
built through the module graph. The file is restored before the script
returns, including on failure.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "studies",
    "estimate-target-density",
    "results_ab",
)
MODULE_FILE = "MODULE.bazel"
PATCH_LINE = '    patches = ["//patches:0001-openroad-gpl-estimate-target-density-11395.patch"],'
DISABLED_LINE = "    # A/B: patches attribute disabled for the baseline arm."

# design directory -> (bazel target, does the flow reach doIncrementalPlace?)
DESIGNS = {
    "mock-alu": ("@orfs//flow/designs/asap7/mock-alu:MockAlu_place", True),
    "riscv32i": ("@orfs//flow/designs/asap7/riscv32i:riscv_top_place", True),
    "gcd": ("@orfs//flow/designs/asap7/gcd:gcd_place", False),
}


def set_arm(arm):
    """Rewrite MODULE.bazel for this arm. Returns the original text."""
    with open(MODULE_FILE) as handle:
        original = handle.read()
    if arm == "patched":
        wanted = original.replace(DISABLED_LINE, PATCH_LINE)
    else:
        wanted = original.replace(PATCH_LINE, DISABLED_LINE)
    if wanted == original and arm == "baseline" and PATCH_LINE in original:
        raise RuntimeError("could not disable the patch line -- check MODULE.bazel")
    with open(MODULE_FILE, "w") as handle:
        handle.write(wanted)
    return original


def odb_path(target):
    """Where bazel put this stage's 3_place.odb."""
    out = subprocess.run(
        ["bazelisk", "cquery", "--output=files", target],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in out.stdout.splitlines():
        if line.strip().endswith("3_place.odb"):
            return line.strip()
    raise RuntimeError("no 3_place.odb among the outputs of " + target)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binary_witness():
    """Build the arm's openroad and record what it is.

    Identical ODBs across the two arms are only evidence if the two arms
    ran different binaries. The digest says they did; the command probe
    says which side of the patch this one is on. Without both, "no
    change" and "no rebuild" are the same observation.
    """
    subprocess.run(["bazelisk", "build", "@openroad//:openroad"], check=True)
    binary = os.path.join("bazel-bin", "external", "openroad+", "openroad")
    # A script file, not stdin: `openroad -no_init -exit -` does not read
    # a script from stdin, so the probe would come back empty for every
    # binary -- which reads exactly like "the patch is not in this one".
    with tempfile.NamedTemporaryFile(
        "w", suffix=".tcl", dir="tmp", delete=False
    ) as handle:
        handle.write("puts COMMAND=[info commands estimate_target_density]\n")
        script = handle.name
    try:
        probe = subprocess.run(
            [binary, "-no_init", "-exit", script],
            capture_output=True,
            text=True,
        )
    finally:
        os.unlink(script)
    has_command = "COMMAND=estimate_target_density" in probe.stdout
    return {"openroad_sha256": sha256(binary), "has_command": has_command}


def run_arm(arm, designs):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    original = set_arm(arm)
    try:
        witness = binary_witness()
        print(
            "{:>8} binary: {} command {}".format(
                arm,
                witness["openroad_sha256"][:16],
                "present" if witness["has_command"] else "absent",
            )
        )
        for design in designs:
            target, reaches = DESIGNS[design]
            started = time.time()
            build = subprocess.run(
                ["bazelisk", "build", "--//:log_timestamps", target],
                capture_output=True,
                text=True,
            )
            record = dict(witness)
            record.update({
                "arm": arm,
                "design": design,
                "target": target,
                "reaches_incremental_place": reaches,
                "returncode": build.returncode,
                "wall_s": time.time() - started,
                "started_utc": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)
                ),
            })
            if build.returncode == 0:
                path = odb_path(target)
                record["odb_sha256"] = sha256(path)
            else:
                record["error"] = _first_error(build.stderr)
            path = os.path.join(RESULTS_DIR, "{}_{}.json".format(arm, design))
            with open(path, "w") as handle:
                json.dump(record, handle, indent=2, sort_keys=True)
                handle.write("\n")
            print(
                "{:>8} {:>10}: {}".format(
                    arm, design, record.get("odb_sha256", record.get("error"))
                )
            )
    finally:
        with open(MODULE_FILE, "w") as handle:
            handle.write(original)


def _first_error(stderr):
    for line in stderr.splitlines():
        if re.search(r"ERROR|-\d{4}\]", line):
            return line.strip()[:300]
    return (stderr.strip().splitlines() or [""])[-1][:300]


def compare():
    rows = []
    for design, (_, reaches) in sorted(DESIGNS.items()):
        loaded = {}
        for arm in ("baseline", "patched"):
            path = os.path.join(RESULTS_DIR, "{}_{}.json".format(arm, design))
            if os.path.exists(path):
                with open(path) as handle:
                    loaded[arm] = json.load(handle)
        if len(loaded) < 2:
            rows.append((design, reaches, "not yet measured"))
            continue
        same = loaded["baseline"].get("odb_sha256") == loaded["patched"].get(
            "odb_sha256"
        )
        # An identical ODB means nothing if both arms ran one binary.
        witnessed = loaded["baseline"].get("openroad_sha256") != loaded[
            "patched"
        ].get("openroad_sha256") and loaded["patched"].get("has_command") and not loaded[
            "baseline"
        ].get("has_command")
        rows.append(
            (
                design,
                reaches,
                ("identical" if same else "DIFFERENT")
                if witnessed
                else "no verdict: the two arms did not run different binaries",
            )
        )
    print("| design | reaches doIncrementalPlace | 3_place.odb |")
    print("| --- | --- | --- |")
    for design, reaches, verdict in rows:
        print("| {} | {} | {} |".format(design, "yes" if reaches else "no", verdict))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=["baseline", "patched"])
    parser.add_argument("--designs", nargs="*", default=sorted(DESIGNS))
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    if args.compare:
        return compare()
    if not args.arm:
        parser.error("pass --arm or --compare")
    run_arm(args.arm, args.designs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
