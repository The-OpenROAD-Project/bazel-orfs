"""One sample: what a single (design, seed, arm) run leaves behind.

A sample is a place -> cts -> grt tail on a frozen floorplan, and
everything this study asks of it is already on disk when it finishes:
ORFS writes a metrics JSON per step (`flow.sh` passes `-metrics
$LOG_DIR/<step>.json`) and the stage logs carry the trajectories the
JSONs summarise away. This module turns that into one flat record, so
the campaign is resumable by file existence and the report can be
regenerated without the runs.

## Two min_periods, and why both are kept

`clk_period - WNS` is what this repo means by minimum period --
check_pareto.py's period axis and
test/pre_route_pessimism/stage_ladder.tcl both read it that way, and the
repair-timing-grt skill's Trap 3 is the argument for quoting it in
picoseconds rather than as a percentage of WNS.

ORFS also reports `report_clock_min_period` as a frequency, which lands
in the metrics JSON as `globalroute__timing__fmax`. It is not the same
number: on asap7/gcd, seed 1, `clk_period - WNS` reads 360.3 ps and
`1/fmax` reads 337.1 ps. The two answer slightly different questions
about the clock network, and a study that quoted whichever was handy
would be comparing them across arms without noticing. Both are recorded,
`min_period_wns` is the one the tables use, and the gap between them is
itself reported.

The clock period comes from the design's SDC through the same parser the
rules corpus uses, so the two halves of this study cannot disagree about
what the constraint was.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys

import gpl_trajectory
import repair_delta

# ORFS's own per-step runtime line, the cheapest runtime signal there is.
# Recorded, never quoted: samples run several-wide, so these are wall
# times on a loaded machine by construction.
_ELAPSED = re.compile(r"Elapsed time: (?P<h>\d+):(?P<m>[0-9.]+)\[h:\]min:sec")

# The stage steps a tail produces, in flow order.
STEPS = [
    "3_1_place_gp_skip_io",
    "3_2_place_iop",
    "3_3_place_gp",
    "3_4_place_resized",
    "3_5_place_dp",
    "4_1_cts",
    "5_1_grt",
]

# Artifacts hashed as the witness that two runs did or did not do the
# same thing. The placement one answers "did the seed land", the route
# one answers "did it still matter three stages later".
WITNESS_ODBS = ["3_3_place_gp.odb", "5_1_grt.odb"]


def sha1(path):
    """First 20 hex digits of a file's SHA-1, or None if absent.

    Args:
        path: the file.

    Returns:
        The prefix, matching the width ORFS prints in its stage summary
        so the two can be compared by eye.
    """
    if not os.path.exists(path):
        return None
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:20]


def elapsed_seconds(text):
    """Wall seconds from ORFS's `Elapsed time:` line.

    Args:
        text: a step log's contents.

    Returns:
        Seconds, or None when the line is absent (a step that failed
        before printing it).
    """
    match = _ELAPSED.search(text)
    if not match:
        return None
    return int(match.group("h")) * 3600 + float(match.group("m"))


def read_metrics(logs_dir):
    """Every step's metrics JSON, keyed by step.

    Args:
        logs_dir: the run's log directory.

    Returns:
        {step: {metric: value}} for the steps that produced a JSON.
    """
    metrics = {}
    for path in sorted(glob.glob(os.path.join(logs_dir, "*.json"))):
        step = os.path.basename(path)[: -len(".json")]
        with open(path) as handle:
            metrics[step] = json.load(handle)
    return metrics


def harvest(logs_dir, results_dir, clk_period, **identity):
    """One sample record.

    Args:
        logs_dir: the run's `logs/<platform>/<design>/<variant>`.
        results_dir: its `results/<platform>/<design>/<variant>`.
        clk_period: the design's clock period, in the SDC's units.
        **identity: platform, design, seed, arm and anything else the
            campaign wants carried through to the tables.

    Returns:
        The record. Missing pieces are None and are visible as such; a
        sample that did not reach grt still harvests what it has, which
        is what makes a failed arm reportable instead of invisible.
    """
    metrics = read_metrics(logs_dir)
    grt = metrics.get("5_1_grt", {})

    setup_ws = grt.get("globalroute__timing__setup__ws")
    fmax = grt.get("globalroute__timing__fmax")
    record = dict(identity)
    record.update(
        {
            "clk_period": clk_period,
            "min_period_wns": (
                clk_period - setup_ws
                if clk_period is not None and setup_ws is not None
                else None
            ),
            # fmax is in Hz and the SDC is in its own units, so this is
            # only comparable to min_period_wns after the caller knows
            # the unit. Kept raw for exactly that reason.
            "fmax_hz": fmax,
            "setup_ws": setup_ws,
            "setup_tns": grt.get("globalroute__timing__setup__tns"),
            "hold_ws": grt.get("globalroute__timing__hold__ws"),
            "hold_tns": grt.get("globalroute__timing__hold__tns"),
            "setup_buffers": grt.get("globalroute__design__instance__count__setup_buffer"),
            "hold_buffers": grt.get("globalroute__design__instance__count__hold_buffer"),
            "wirelength": grt.get("globalroute__global_route__wirelength"),
            "displacement_max": grt.get("globalroute__design__instance__displacement__max"),
            "drc": grt.get("globalroute__design__violations"),
        }
    )

    runtimes = {}
    for step in STEPS:
        log = os.path.join(logs_dir, "%s.log" % step)
        if os.path.exists(log):
            with open(log, errors="replace") as handle:
                runtimes[step] = elapsed_seconds(handle.read())
    record["runtime_s"] = runtimes

    place_log = os.path.join(logs_dir, "3_3_place_gp.log")
    if os.path.exists(place_log):
        with open(place_log, errors="replace") as handle:
            record["trajectory"] = gpl_trajectory.signature(handle.read())

    grt_log = os.path.join(logs_dir, "5_1_grt.log")
    if os.path.exists(grt_log):
        with open(grt_log, errors="replace") as handle:
            record["repair"] = repair_delta.summarize_log(handle.read())

    record["witness"] = {
        name: sha1(os.path.join(results_dir, name)) for name in WITNESS_ODBS
    }
    record["metrics"] = metrics
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--clk-period", type=float, required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--design", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--arm", default="base")
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args(argv)

    record = harvest(
        args.logs_dir,
        args.results_dir,
        args.clk_period,
        platform=args.platform,
        design=args.design,
        seed=args.seed,
        arm=args.arm,
    )
    os.makedirs(os.path.dirname(args.out_json) or ".", exist_ok=True)
    with open(args.out_json, "w") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        "%s/%s seed %d arm %s: min_period %s"
        % (
            args.platform,
            args.design,
            args.seed,
            args.arm,
            record["min_period_wns"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
