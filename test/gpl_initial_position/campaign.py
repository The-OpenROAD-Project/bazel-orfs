"""Run the arms: one deployed tree per design, many samples, one JSON each.

The unit of work is a `place` stage -- optionally continued through
`cts` and `grt` -- on a frozen floorplan. `bazelisk run //:deps --
<target>_place` deploys the tree once; every sample then runs inside it
under its own `FLOW_VARIANT`, so all samples for a design share the
synthesis and floorplan bytes and differ only in the arm and the seed.
That is what makes a couple of thousand samples affordable: no bazel
analysis per leaf, no re-synthesis, and the tree doubles as the
reproducer anyone else can be handed.

Resumability is by file existence -- a sample whose JSON is present is
not re-run -- so the campaign can be interrupted, extended with more
seeds, or restarted after a crash with no bookkeeping.

## Two tiers, because the two endpoints have different noise

* `--tier place` stops after the place stage. Its endpoints --
  `gp_hpwl_final` and `gp_iterations` -- do not depend on machine load,
  so these samples run several-wide.

* `--tier tail` continues to global route for the timing and congestion
  endpoints, and costs about 3.5x as much per sample.

Wall time is a third endpoint and it is the one that cannot be measured
several-wide at all. `--serial` runs one sample at a time and refuses to
start one while the machine is busy, so a `gp_wall_s` from a serial run
means something and a `gp_wall_s` from a wide run is recorded but never
quoted. Which of the two produced a sample is stored in the record.
"""

import argparse
import concurrent.futures
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

import harvest

# The arms. `shipped` is ORFS as it stands today and is the baseline
# every other arm is compared against: no `-initial_position_mode`, so
# global placement takes ODB positions at `3_1_place_gp_skip_io` and is
# forced to the core center at `3_3_place_gp` by the
# `-force_center_initial_place` ORFS appends unconditionally.
#
# `center` is not a synonym for it: `center` applies one policy at both
# calls, which is what "the flow has a position policy" would actually
# mean. The gap between `shipped` and `center` is the cost of ORFS's
# split, and it is a result in its own right.
ARMS = {
    "shipped": [],
    "center": ["-initial_position_mode center"],
    "odb": ["-initial_position_mode odb"],
    "corner_ll": ["-initial_position_mode corner_ll"],
    "corner_ur": ["-initial_position_mode corner_ur"],
    "uniform": ["-initial_position_mode uniform"],
    "gauss_tight": ["-initial_position_mode gauss_tight"],
    "gauss_wide": ["-initial_position_mode gauss_wide"],
    "spread": ["-initial_position_mode spread"],
    "anchored": ["-initial_position_mode anchored"],
}

BASELINE_ARM = "shipped"

# The arms whose start position is itself a draw. Their spread has a
# component the deterministic arms do not have, so it is part of the
# result rather than a nuisance -- and they are sized with more seeds
# for exactly that reason.
STOCHASTIC_ARMS = ("uniform", "gauss_tight", "gauss_wide")

# A variant starts as a copy of the frozen prefix: everything the
# deployed tree staged, minus anything this sample is supposed to
# produce. Copying the directory rather than a hand-picked list is
# deliberate -- a missing .short.mk or .analysis.json turns into a
# rebuild of a stage the campaign is supposed to be sharing, silently
# and only on some designs -- and the exclusions are what stop a stale
# output from being mistaken for this sample's.
TAIL_OUTPUT_PREFIXES = ("3_1_", "3_2_", "3_3_", "3_4_", "3_5_", "4_", "5_", "route.guide")

TAIL_OUTPUT_EXACT = ("3_place.odb", "3_place.sdc")

_LITERAL_PERIOD = re.compile(r"create_clock[^\n]*?-period\s+([0-9.]+)")


def find_design_root(tree, platform, design):
    """The directory inside a deployed tree that holds results/ and logs/.

    Args:
        tree: the `*_deps` directory `//:deps` wrote.
        platform: PDK name.
        design: design directory name.

    Returns:
        The path.

    Raises:
        SystemExit: when zero or several match, rather than guessing
            which tree the samples should land in.
    """
    pattern = os.path.join(tree, "*", "flow", "designs", platform, design)
    matches = [path for path in glob.glob(pattern) if os.path.isdir(path)]
    if len(matches) != 1:
        sys.exit(
            "expected exactly one %s/%s under %s, found %d"
            % (platform, design, tree, len(matches))
        )
    return matches[0]


def results_name(design_root, platform):
    """What ORFS calls this design under results/ and logs/.

    Not the design directory: ORFS keys those paths on DESIGN_NICKNAME,
    which defaults to DESIGN_NAME, so `flow/designs/asap7/aes` writes to
    `results/asap7/aes_cipher_top`. Detected rather than configured --
    the frozen `base` directory has to exist, so the directory holding
    it is by definition the right one.

    Args:
        design_root: from find_design_root().
        platform: PDK name.

    Returns:
        The name.

    Raises:
        SystemExit: when zero or several candidates carry a `base`,
            rather than writing a sample where the flow will not read it.
    """
    parent = os.path.join(design_root, "results", platform)
    candidates = [
        name
        for name in sorted(os.listdir(parent))
        if os.path.isdir(os.path.join(parent, name, "base"))
    ]
    if len(candidates) != 1:
        sys.exit(
            "expected exactly one design under %s with a frozen base/, found %s"
            % (parent, candidates)
        )
    return candidates[0]


def prepare_variant(design_root, platform, design, variant):
    """Copy the frozen prefix into a fresh variant directory.

    Args:
        design_root: from find_design_root().
        platform: PDK name.
        design: the name ORFS uses under results/, from results_name().
        variant: the FLOW_VARIANT this sample runs under.

    Returns:
        (results_dir, logs_dir) for the variant.
    """
    results = os.path.join(design_root, "results", platform, design)
    logs = os.path.join(design_root, "logs", platform, design)
    base = os.path.join(results, "base")
    target = os.path.join(results, variant)
    # A fresh directory, not an updated one. Leaving a previous run's
    # outputs in place would let make decide the stage is already built
    # and skip it, and the sample would then be harvested from the old
    # run under a new name -- the one failure here that produces a
    # plausible number instead of an error.
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)
    for name in sorted(os.listdir(base)):
        if name.startswith(TAIL_OUTPUT_PREFIXES) or name in TAIL_OUTPUT_EXACT:
            continue
        source = os.path.join(base, name)
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(target, name))
    return target, os.path.join(logs, variant)


def clock_from_frozen_sdc(results_dir):
    """The clock period this sample actually ran under.

    Read from the variant's own copy of `2_floorplan.sdc` rather than
    from the design source, so the recorded period is the one the run
    used and is the same file for every arm by construction.

    Args:
        results_dir: the variant's results directory.

    Returns:
        The period in the SDC's units, or None when there is no literal
        `create_clock -period` to read.
    """
    path = os.path.join(results_dir, "2_floorplan.sdc")
    if not os.path.exists(path):
        return None
    with open(path, errors="replace") as handle:
        match = _LITERAL_PERIOD.search(handle.read())
    return float(match.group(1)) if match else None


def wait_for_idle(threshold, timeout_s=1800, poll_s=15):
    """Block until the 1-minute load average drops below `threshold`.

    A concurrent compile is the difference between a runtime measurement
    and a runtime anecdote, so a serial sample refuses to start on a busy
    machine instead of recording a number it cannot defend.

    Args:
        threshold: the 1-minute load average to get under.
        timeout_s: give up waiting after this long.
        poll_s: how often to look.

    Returns:
        The load average the sample actually started at.

    Raises:
        SystemExit: on timeout. Refusing to record beats recording
            something that will later be quoted.
    """
    deadline = time.time() + timeout_s
    while True:
        load = os.getloadavg()[0]
        if load < threshold:
            return load
        if time.time() > deadline:
            sys.exit(
                "load average %.2f never fell below %.2f in %ds; refusing to "
                "record a serial runtime sample" % (load, threshold, timeout_s)
            )
        time.sleep(poll_s)


def run_sample(
    tree,
    design_root,
    platform,
    design,
    arm,
    seed,
    cores,
    out_dir,
    timeout_s,
    tier="place",
    serial=False,
    max_loadavg=None,
    cpu_list=None,
):
    """Run one sample and harvest it, or skip it if already done.

    Args:
        tree: the deployed tree, which holds the `make` wrapper.
        design_root: from find_design_root().
        platform, design: identity.
        arm: a key of ARMS; also the variant prefix.
        seed: GPL_RANDOM_SEED for this sample.
        cores: NUM_CORES, held equal across every sample.
        out_dir: where the sample JSON goes.
        timeout_s: give up on a sample after this long.
        tier: "place" stops after the place stage, "tail" continues
            through cts and grt.
        serial: this sample's wall time is meant to be quotable.
        max_loadavg: refuse to start a serial sample above this load.
        cpu_list: a `taskset -c` list, so serial samples always get the
            same cores and their wall times are comparable.

    Returns:
        The output path, or None when the sample was already harvested.
    """
    variant = "%s_s%d" % (arm, seed)
    out_json = os.path.join(out_dir, "%s_%s_%s.json" % (platform, design, variant))
    if os.path.exists(out_json):
        return None

    name = results_name(design_root, platform)
    results_dir, logs_dir = prepare_variant(design_root, platform, name, variant)
    clk_period = clock_from_frozen_sdc(results_dir)

    targets = ["do-place"] if tier == "place" else ["do-place", "do-cts", "do-grt"]
    command = [os.path.join(tree, "make")] + targets + [
        "GPL_RANDOM_SEED=%d" % seed,
        "FLOW_VARIANT=%s" % variant,
        "NUM_CORES=%d" % cores,
        "GLOBAL_PLACEMENT_ARGS=%s" % " ".join(ARMS[arm]),
    ]
    if cpu_list:
        command = ["taskset", "-c", cpu_list] + command

    if serial and max_loadavg is not None:
        loadavg = wait_for_idle(max_loadavg)
    else:
        loadavg = os.getloadavg()[0]

    started = time.time()
    os.makedirs(logs_dir, exist_ok=True)
    with open(os.path.join(logs_dir, "campaign.log"), "w") as handle:
        try:
            status = subprocess.call(
                command, stdout=handle, stderr=subprocess.STDOUT, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            status = "timeout"
    wall = time.time() - started

    record = harvest.harvest(
        logs_dir,
        results_dir,
        clk_period,
        platform=platform,
        design=design,
        arm=arm,
        seed=seed,
        variant=variant,
    )
    record["run"] = {
        "status": status,
        "wall_s": wall,
        "loadavg_at_start": loadavg,
        "cores": cores,
        "tier": tier,
        "serial": serial,
        "cpu_list": cpu_list,
        # The command with the tree path stripped: a sample record is
        # published, and a local path is not.
        "command": [part.replace(tree, "<tree>") for part in command],
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(out_json, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return out_json


def parse_seeds(text):
    """Expand a seed specification.

    Args:
        text: e.g. "1-16", "1,2,5", "1-4,9".

    Returns:
        The list of seeds, in the order written.
    """
    seeds = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            seeds.extend(range(int(low), int(high) + 1))
        else:
            seeds.append(int(part))
    return seeds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, help="a *_deps directory")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--design", required=True)
    parser.add_argument("--seeds", default="1-16")
    parser.add_argument(
        "--stochastic-seeds",
        default=None,
        help="seeds for the arms whose start position is itself a draw; "
        "defaults to --seeds",
    )
    parser.add_argument(
        "--arms",
        default=",".join(ARMS),
        help="comma-separated arm names; default is all of them",
    )
    parser.add_argument("--tier", choices=["place", "tail"], default="place")
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--jobs", type=int, default=4, help="samples in parallel")
    parser.add_argument("--timeout-s", type=int, default=7200)
    parser.add_argument(
        "--serial",
        action="store_true",
        help="one sample at a time, gated on an idle machine, so the "
        "recorded wall time is quotable",
    )
    parser.add_argument("--max-loadavg", type=float, default=2.0)
    parser.add_argument("--cpu-list", default=None, help="taskset -c list")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    arms = [name.strip() for name in args.arms.split(",") if name.strip()]
    unknown = [name for name in arms if name not in ARMS]
    if unknown:
        sys.exit("unknown arms: %s; known: %s" % (unknown, sorted(ARMS)))

    seeds = parse_seeds(args.seeds)
    stochastic = (
        parse_seeds(args.stochastic_seeds) if args.stochastic_seeds else seeds
    )

    design_root = find_design_root(args.tree, args.platform, args.design)
    os.makedirs(args.out_dir, exist_ok=True)

    work = [
        (arm, seed)
        for arm in arms
        for seed in (stochastic if arm in STOCHASTIC_ARMS else seeds)
    ]

    jobs = 1 if args.serial else args.jobs
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(
                run_sample,
                args.tree,
                design_root,
                args.platform,
                args.design,
                arm,
                seed,
                args.cores,
                args.out_dir,
                args.timeout_s,
                args.tier,
                args.serial,
                args.max_loadavg,
                args.cpu_list,
            ): (arm, seed)
            for arm, seed in work
        }
        for future in concurrent.futures.as_completed(futures):
            arm, seed = futures[future]
            path = future.result()
            if path is None:
                print("%s seed %d: already harvested" % (arm, seed))
            else:
                done += 1
                print("%s seed %d -> %s" % (arm, seed, os.path.basename(path)))

    print(
        "%s/%s: %d new samples, %d requested, in %s"
        % (args.platform, args.design, done, len(work), args.out_dir)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
