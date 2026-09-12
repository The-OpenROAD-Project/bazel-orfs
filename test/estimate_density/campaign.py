"""Walk the density ladder for a design and record one file per rung.

The threshold this study is after -- the lowest density at which global
placement still reaches its overflow target -- is a boolean per rung, so
the campaign is a bisection: a coarse ladder first, then halve the
interval that flips, until the bracket is one rung wide.

Every rung is a `bazelisk build` of a manual target declared in
BUILD.bazel, so a refinement is a build rather than an edit, and a rung
already recorded is never re-run. Results land as
`results/<design>_t<ii>.json`, one file per sample, which is what makes
the campaign resumable and what lets report.py discover -- rather than
be told -- what has been measured.

Usage:

    python3 test/estimate_density/campaign.py --design gcd
    python3 test/estimate_density/campaign.py --design gcd --rung 8 --repeat 3

Run it from the workspace root; it shells out to bazelisk and reads the
stage log out of the build outputs.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harvest  # noqa: E402

PACKAGE = "//test/estimate_density"
# Samples live with the study's other artifacts, not beside the code
# that writes them: they are the study's data, they are committed on the
# study branch, and report.py finds them there by default.
RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "studies",
    "estimate-target-density",
    "results",
)
RUNG_COUNT = 32

# The coarse ladder, in rung indices. Wide enough that one of them lands
# above the threshold for a design that needs almost no help, cheap
# enough that a design needing a lot of it is bracketed in five runs.
COARSE = [0, 8, 16, 24, 31]

# Design directory -> Verilog top. ORFS names the results directory after
# the top, not after the design directory or the bazel target, so finding
# a rung's log needs both halves. campaign_test.py asserts this agrees
# with STUDY_DESIGNS in BUILD.bazel, which is what actually declares the
# arms.
DESIGN_TOPS = {
    "gcd": "gcd",
    "uart": "uart",
    "mock-alu": "MockAlu",
    "riscv32i": "riscv_top",
    "mock-cpu": "mock_cpu",
    "aes": "aes_cipher_top",
    "jpeg": "jpeg_encoder",
    "ethmac": "ethmac",
}


def rung_variant(rung, prefix=""):
    """FLOW_VARIANT of a rung -- rungs.bzl's rung_variant(), in python."""
    return "{}t{:02d}".format(prefix, rung)


def rung_target(design, rung, prefix=""):
    return "{}:{}_{}_place".format(PACKAGE, design, rung_variant(rung, prefix))


def rung_density_fraction(rung):
    return rung / float(RUNG_COUNT)


def loadavg():
    with open("/proc/loadavg") as handle:
        return float(handle.read().split()[0])


def find_stage_log(design, variant):
    """The 3_3_place_gp.log this rung's build just produced.

    Located by walking the package's output tree rather than by
    reconstructing ORFS's path layout: the layout is ORFS's to change,
    and a wrong guess here would read a stale log from another rung,
    which is the one failure that would not look like a failure.
    """
    root = os.path.join("bazel-bin", "test", "estimate_density")
    # The variant directory, not the target name: ORFS writes to
    # results/<platform>/<design>/<variant>/, and the target name appears
    # nowhere in that path.
    wanted = variant
    hits = []
    for dirpath, _, filenames in os.walk(root):
        if "3_3_place_gp.log" not in filenames:
            continue
        parts = dirpath.split(os.sep)
        # A stage target also stages its logs into a .runfiles tree, so
        # every log exists twice; the copy is the same bytes today and
        # there is no reason to depend on that.
        if any(part.endswith(".runfiles") for part in parts):
            continue
        if wanted not in parts or DESIGN_TOPS[design] not in parts:
            continue
        hits.append(os.path.join(dirpath, "3_3_place_gp.log"))
    if len(hits) != 1:
        raise RuntimeError(
            "expected exactly one 3_3_place_gp.log for {}, found {}".format(
                wanted, hits
            )
        )
    return hits[0]


# What ORFS's own report_metrics wrote for the global place substep.
# Reading these rather than recomputing anything is the whole point: the
# flow already states its wirelength, slack and area, so the study never
# has to form an opinion about how to measure them.
METRICS_WANTED = [
    "globalplace__gpl__convergence__iteration",
    "globalplace__gpl__area__final",
    "globalplace__gpl__routability__congestion",
    "globalplace__route__wirelength__estimated",
    "globalplace__timing__setup__ws",
    "globalplace__timing__setup__tns",
]


def stage_metrics(log_path):
    """The metrics JSON ORFS wrote beside this stage log."""
    path = log_path[: -len(".log")] + ".json"
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        data = json.load(handle)
    return {key: data[key] for key in METRICS_WANTED if key in data}


def run_variant(design, variant, repeat, jobs, keep_going=False, extra=None):
    """Build one arm -- a rung, or `ship`/`est` -- and record its log."""
    target = "{}:{}_{}_place".format(PACKAGE, design, variant)
    path = os.path.join(RESULTS_DIR, "{}_{}_r{}.json".format(design, variant, repeat))
    if os.path.exists(path):
        with open(path) as handle:
            return json.load(handle)

    command = ["bazelisk", "build", "--//:log_timestamps", target]
    if jobs:
        command.insert(2, "--jobs={}".format(jobs))

    load_before = loadavg()
    started = time.time()
    completed = subprocess.run(command, capture_output=True, text=True)
    wall = time.time() - started

    record = {
        "design": design,
        "variant": variant,
        "repeat": repeat,
        "target": target,
        "bazel_returncode": completed.returncode,
        "wall_s": wall,
        "loadavg_at_start": load_before,
        "loadavg_at_end": loadavg(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
    }

    if completed.returncode != 0:
        record["error"] = _first_error(completed.stderr)
        # A rung above the top of its design's range is not a failed
        # placement: ORFS refuses before global placement runs
        # (FLW-0024, "Place density exceeds 1.0"). Recording that as a
        # miss would put a threshold where there is only arithmetic, so
        # it is marked and the bisection steps over it.
        record["out_of_range"] = _density_out_of_range(design, variant)
        if not keep_going and not record["out_of_range"]:
            _write(path, record)
            raise RuntimeError(
                "{} failed to build: {}".format(target, record["error"])
            )
    else:
        log = find_stage_log(design, variant)
        with open(log) as handle:
            text = handle.read()
        record.update(harvest.harvest(text))
        record["metrics"] = stage_metrics(log)

    _write(path, record)
    return record


def _density_out_of_range(design, variant):
    """Did ORFS refuse this arm because the density came out above 1.0?"""
    root = os.path.join("bazel-bin", "test", "estimate_density", "logs")
    for dirpath, _, names in os.walk(root):
        parts = dirpath.split(os.sep)
        if any(part.endswith(".runfiles") for part in parts):
            continue
        if variant not in parts or DESIGN_TOPS[design] not in parts:
            continue
        for name in names:
            with open(os.path.join(dirpath, name), errors="replace") as handle:
                if "FLW-0024" in handle.read():
                    return True
    return False


def _first_error(stderr):
    for line in stderr.splitlines():
        if re.search(r"ERROR|FLW-\d+|GPL-\d+", line):
            return _scrub(line.strip()[:300])
    return _scrub(stderr.strip().splitlines()[-1][:300]) if stderr.strip() else ""

def _scrub(text):
    """Strip this machine out of a message before it is recorded.

    A failing arm's message is bazel's, and bazel names absolute paths in
    the workspace. Samples are committed and published, so the workspace
    prefix is replaced with a placeholder here rather than being
    remembered at publication time.
    """
    return text.replace(os.getcwd(), "<workspace>")



def _write(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")


def converged(record):
    gp = record.get("gp")
    return bool(gp and gp["converged"])


def _rung(design, rung, repeat, jobs):
    """One rung's verdict: hit, miss, or out of range."""
    record = run_variant(design, rung_variant(rung), repeat, jobs, keep_going=True)
    if record.get("out_of_range"):
        return "out of range"
    return "hit" if converged(record) else "miss"


def bisect(design, jobs, repeat=0):
    """Coarse ladder, then halve the interval that flips.

    Returns the bracket [highest rung that missed, lowest rung that hit].
    A design that converges at rung 0 needs no density help at all and
    says so; one that misses at every rung has no threshold inside the
    ladder, which is equally a result.
    """
    seen = {}
    for rung in COARSE:
        seen[rung] = _rung(design, rung, repeat, jobs)
        print("{} rung {:2d}: {}".format(design, rung, seen[rung]))
    seen = {rung: ok for rung, ok in seen.items() if ok != "out of range"}

    hits = sorted(rung for rung, ok in seen.items() if ok == "hit")
    if not hits:
        # Either nothing converged, or nothing was measurable at all --
        # a design whose uniform density is already so high that every
        # rung lands above 1.0. They are different results and the
        # bracket has to be able to say which.
        return (max(seen) if seen else None, None)
    low = max(
        [rung for rung, ok in seen.items() if ok == "miss" and rung < hits[0]] or [-1]
    )
    high = hits[0]

    while high - low > 1:
        middle = (low + high) // 2
        ok = _rung(design, middle, repeat, jobs)
        seen[middle] = ok
        print("{} rung {:2d}: {}".format(design, middle, ok))
        if ok == "out of range":
            # Density rises with the rung, so a rung below one that built
            # cannot itself be above 1.0. Reaching here means the ladder
            # is not monotone in the way the bisection assumes, and the
            # bracket it would return would be a fiction.
            raise RuntimeError(
                "rung {} of {} is out of range although rung {} built: "
                "the ladder is not monotone".format(middle, design, high)
            )
        if ok == "hit":
            high = middle
        else:
            low = middle
    return (low if low >= 0 else None, high)


def sweep(designs, jobs, repeat=0):
    """Every design, fastest first: the two named arms, then the ladder.

    A design that cannot be built at all is recorded and stepped over
    rather than ending the campaign: the point of one file per sample is
    that a night of running leaves whatever it managed, and the report
    says plainly which designs are still missing.
    """
    for design in designs:
        print("=== {}".format(design), flush=True)
        try:
            for arm in ("ship", "est"):
                record = run_variant(design, arm, repeat, jobs, keep_going=True)
                gp = record.get("gp") or {}
                print(
                    "{} {}: density {} converged {} iters {}".format(
                        design,
                        arm,
                        record.get("driven_density")
                        or (record.get("context") or {}).get("place_density"),
                        gp.get("converged"),
                        gp.get("iterations"),
                    ),
                    flush=True,
                )
            print("{}: bracket {}".format(design, bisect(design, jobs, repeat)), flush=True)
        except Exception as failure:  # noqa: BLE001 -- a design is not the campaign
            print("{}: FAILED {}".format(design, failure), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--design",
        default=None,
        help="one design; omit with --all to sweep every design",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="sweep every design in DESIGN_TOPS, fastest first",
    )
    parser.add_argument(
        "--rung",
        type=int,
        default=None,
        help="run this rung only, instead of bisecting for the threshold",
    )
    parser.add_argument(
        "--arm",
        default=None,
        help="run a named arm (ship, est) instead of a rung or a bisection",
    )
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument(
        "--jobs",
        default=None,
        help="passed to bazelisk, to keep a measured run off every core",
    )
    args = parser.parse_args()

    if args.all:
        sweep(list(DESIGN_TOPS), args.jobs, args.repeat)
        return 0
    if not args.design:
        parser.error("pass --design or --all")

    if args.arm:
        record = run_variant(args.design, args.arm, args.repeat, args.jobs)
        print(json.dumps({k: v for k, v in record.items() if k != "gp"}, indent=2))
        if record.get("gp"):
            print("converged:", record["gp"]["converged"])
        return 0

    if args.rung is not None:
        record = run_variant(
            args.design, rung_variant(args.rung), args.repeat, args.jobs
        )
        print(json.dumps({k: v for k, v in record.items() if k != "gp"}, indent=2))
        if record.get("gp"):
            print("converged:", record["gp"]["converged"])
        return 0

    bracket = bisect(args.design, args.jobs, args.repeat)
    print("{}: threshold bracket (miss, hit) = {}".format(args.design, bracket))
    return 0


if __name__ == "__main__":
    sys.exit(main())
