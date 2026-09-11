"""Run the ensemble: one deployed tree, many seeds, one JSON per sample.

The unit of work is a place -> cts -> grt tail on a frozen floorplan.
`bazelisk run //:deps -- <target>_place` deploys the tree once; every
sample then runs inside it under its own `FLOW_VARIANT`, so the samples
share the synthesis and floorplan byte for byte and differ only in the
knob under test. That is what makes an ensemble affordable: no bazel
analysis per leaf, no re-synthesis, and the tree is also the reproducer
anyone else can be handed.

Resumability is by file existence -- a sample whose JSON is present is
not re-run -- so the campaign can be interrupted, extended with more
seeds, or restarted after a crash without bookkeeping.

## What is deliberately not controlled

Samples run several-wide. Placement results do not depend on machine
load, and every arm's determinism is checked separately (the same seed
twice must produce a byte-identical ODB), so running them concurrently
costs nothing this study measures. It does make every `runtime_s` a wall
time on a loaded machine: recorded, never quoted. `loadavg` at sample
start is stored alongside so a runtime claim can never be made by
accident from data that cannot support one.

Thread count *is* controlled, because it can change results: every
sample is run with the same `NUM_CORES`, and the value is recorded in
the sample.
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
import rules_corpus

# A variant starts as a copy of the frozen prefix: everything the
# deployed tree staged, minus anything the tail is supposed to produce.
# Copying the whole directory rather than a hand-picked list is
# deliberate -- a missing .short.mk or .analysis.json turns into a
# rebuild of a stage the ensemble is supposed to be sharing, silently
# and only on some designs -- and the exclusions are what stop a stale
# output from being mistaken for this sample's.
TAIL_OUTPUT_PREFIXES = ("3_1_", "3_2_", "3_3_", "3_4_", "3_5_", "4_", "5_", "route.guide")

TAIL_OUTPUT_EXACT = ("3_place.odb", "3_place.sdc")


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
    the frozen `base` directory is the thing that has to exist, so the
    directory containing it is by definition the right one.

    Args:
        design_root: from find_design_root().
        platform: PDK name.

    Returns:
        The name.

    Raises:
        SystemExit: when zero or several candidates carry a `base`,
            rather than writing a sample into a directory the flow will
            not read.
    """
    parent = os.path.join(design_root, "results", platform)
    candidates = [
        name
        for name in sorted(os.listdir(parent))
        if os.path.isdir(os.path.join(parent, name, "base"))
    ]
    if len(candidates) != 1:
        sys.exit(
            "expected exactly one design under %s with a frozen base/, "
            "found %s" % (parent, candidates)
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
    os.makedirs(target, exist_ok=True)
    for name in sorted(os.listdir(base)):
        if name.startswith(TAIL_OUTPUT_PREFIXES) or name in TAIL_OUTPUT_EXACT:
            continue
        source = os.path.join(base, name)
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(target, name))
    return target, os.path.join(logs, variant)


def retighten_sdc(results_dir, period):
    """Rewrite the variant's frozen SDC to a different clock period.

    An arm that tightens the clock is not a different design: synthesis
    and the floorplan are the same frozen bytes every other arm starts
    from, and only the constraint the tail is asked to hit changes. That
    is deliberate and it is the caveat -- the floorplan was built for
    the looser clock, so a tightened arm measures what place, cts and
    global route can do with a floorplan chosen for something else,
    which is also what a designer tightening a clock actually faces.

    Every `create_clock -period` in the file is rewritten, so a design
    with a virtual IO clock keeps the two in step.

    Args:
        results_dir: the variant's results directory.
        period: the new period, in the SDC's units.

    Returns:
        The number of clocks rewritten.

    Raises:
        SystemExit: when there is no frozen SDC to rewrite, rather than
            running the arm at the stock clock and labelling it
            otherwise.
    """
    path = os.path.join(results_dir, "2_floorplan.sdc")
    if not os.path.exists(path):
        sys.exit("no 2_floorplan.sdc in %s to retighten" % results_dir)
    with open(path) as handle:
        text = handle.read()
    text, count = re.subn(
        r"(create_clock[^\n]*?-period\s+)[0-9.]+",
        lambda match: "%s%.4f" % (match.group(1), period),
        text,
    )
    if not count:
        sys.exit("no literal create_clock -period in %s" % path)
    with open(path, "w") as handle:
        handle.write(text)
    return count


def clock_from_frozen_sdc(results_dir, design_root):
    """The clock period this sample actually ran under.

    The deployed tree carries no design sources -- the constraint has
    already been elaborated into `2_floorplan.sdc` next to the frozen
    floorplan, with the period as a literal. Reading that rather than
    the design's `constraint.sdc` means the recorded period is the one
    the run used, not the one the source implies, and it is the same
    file for every seed by construction.

    Args:
        results_dir: the variant's results directory, holding the copy
            of the frozen `2_floorplan.sdc`.
        design_root: fallback, for a tree that does ship sources.

    Returns:
        (period, source) as rules_corpus.clock_from_sdc does.
    """
    frozen = os.path.join(results_dir, "2_floorplan.sdc")
    if os.path.exists(frozen):
        with open(frozen) as handle:
            match = rules_corpus.LITERAL_PERIOD.search(handle.read())
        if match:
            return float(match.group(1)), "2_floorplan.sdc"
    return rules_corpus.clock_from_sdc(design_root)


def reharvest(design_root, platform, design, seed, arm, out_dir):
    """Re-read an already-run sample's logs without re-running it.

    The parsers outlive the runs: a screen that gains a column, or a
    regression flag that becomes per-metric, must not cost an hour of
    flow time to apply to samples already on disk. The run block is
    carried over from the existing record so a re-harvested sample still
    says what it was run with.

    Args:
        design_root: from find_design_root().
        platform, design, seed, arm: identity.
        out_dir: where the sample JSON lives.

    Returns:
        The path, or None when there is nothing to re-read.
    """
    variant = "%s_s%d" % (arm, seed)
    out_json = os.path.join(out_dir, "%s_%s_%s.json" % (platform, design, variant))
    if not os.path.exists(out_json):
        return None
    with open(out_json) as handle:
        previous = json.load(handle)
    name = results_name(design_root, platform)
    results_dir = os.path.join(design_root, "results", platform, name, variant)
    logs_dir = os.path.join(design_root, "logs", platform, name, variant)
    clk_period, _ = clock_from_frozen_sdc(results_dir, design_root)
    record = harvest.harvest(
        logs_dir,
        results_dir,
        clk_period,
        platform=platform,
        design=design,
        seed=seed,
        arm=arm,
        variant=variant,
    )
    record["run"] = previous.get("run", {})
    with open(out_json, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return out_json


def run_sample(tree, design_root, platform, design, seed, arm, knobs, cores,
               out_dir, timeout_s, sdc_period=None):
    """Run one sample and harvest it, or report why it did not run.

    Args:
        tree: the deployed tree (holds the `make` wrapper).
        design_root: from find_design_root().
        platform, design: identity.
        seed: GPL_RANDOM_SEED for this sample.
        arm: the arm's name, which is also the variant prefix.
        knobs: extra `VAR=value` make arguments defining the arm.
        cores: NUM_CORES, held equal across every sample.
        out_dir: where the sample JSON goes.
        timeout_s: give up on a sample after this long.

    Returns:
        The output path, or None when the sample was skipped.
    """
    variant = "%s_s%d" % (arm, seed)
    out_json = os.path.join(out_dir, "%s_%s_%s.json" % (platform, design, variant))
    if os.path.exists(out_json):
        return None

    results_dir, logs_dir = prepare_variant(
        design_root, platform, results_name(design_root, platform), variant
    )
    if sdc_period is not None:
        retighten_sdc(results_dir, sdc_period)
    clk_period, sdc_source = clock_from_frozen_sdc(results_dir, design_root)

    command = [
        os.path.join(tree, "make"),
        "do-place",
        "do-cts",
        "do-grt",
        "GPL_RANDOM_SEED=%d" % seed,
        "FLOW_VARIANT=%s" % variant,
        "NUM_CORES=%d" % cores,
    ] + list(knobs)

    loadavg = os.getloadavg()[0]
    started = time.time()
    log_path = os.path.join(logs_dir, "campaign.log")
    os.makedirs(logs_dir, exist_ok=True)
    with open(log_path, "w") as handle:
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
        seed=seed,
        arm=arm,
        variant=variant,
    )
    record["run"] = {
        "status": status,
        "wall_s": wall,
        "loadavg_at_start": loadavg,
        "cores": cores,
        "knobs": list(knobs),
        "clk_period_source": sdc_source,
        # The command with the tree path stripped: a sample record is
        # published, and a local path is not.
        "command": [part.replace(tree, "<tree>") for part in command],
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(out_json, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return out_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, help="a *_deps directory")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--design", required=True)
    parser.add_argument("--seeds", required=True, help="e.g. 1-16 or 1,2,5")
    parser.add_argument("--arm", default="base")
    parser.add_argument(
        "--knob",
        action="append",
        default=[],
        help="extra make VAR=value defining the arm; repeatable",
    )
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--jobs", type=int, default=4, help="samples in parallel")
    parser.add_argument("--timeout-s", type=int, default=7200)
    parser.add_argument(
        "--sdc-period",
        type=float,
        default=None,
        help="rewrite the frozen SDC's clock period for this arm, in the "
        "SDC's own units; the floorplan is unchanged",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--reharvest",
        action="store_true",
        help="re-read the logs of samples already on disk and rewrite "
        "their JSON; runs nothing",
    )
    args = parser.parse_args(argv)

    seeds = []
    for part in args.seeds.split(","):
        if "-" in part:
            low, high = part.split("-")
            seeds.extend(range(int(low), int(high) + 1))
        else:
            seeds.append(int(part))

    design_root = find_design_root(args.tree, args.platform, args.design)
    os.makedirs(args.out_dir, exist_ok=True)

    if args.reharvest:
        done = 0
        for seed in seeds:
            if reharvest(
                design_root, args.platform, args.design, seed, args.arm, args.out_dir
            ):
                done += 1
        print("re-harvested %d samples in %s" % (done, args.out_dir))
        return 0

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(
                run_sample,
                args.tree,
                design_root,
                args.platform,
                args.design,
                seed,
                args.arm,
                args.knob,
                args.cores,
                args.out_dir,
                args.timeout_s,
                args.sdc_period,
            ): seed
            for seed in seeds
        }
        for future in concurrent.futures.as_completed(futures):
            seed = futures[future]
            path = future.result()
            if path is None:
                print("seed %d: already harvested" % seed)
                continue
            done += 1
            with open(path) as handle:
                record = json.load(handle)
            print(
                "seed %d: status %s min_period %s wall %.1fs"
                % (
                    seed,
                    record["run"]["status"],
                    record["min_period_wns"],
                    record["run"]["wall_s"],
                )
            )
    print("%d new samples in %s" % (done, args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
