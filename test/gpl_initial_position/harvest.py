"""One sample: what a single (design, arm, seed) run leaves behind.

A sample is a `place` stage -- optionally continued through `cts` and
`grt` -- on a frozen floorplan. Everything this study asks of it is
already on disk when it finishes: ORFS writes a metrics JSON per step
and the stage logs carry the trajectories those JSONs summarise away.
This module flattens that into one record, so the campaign is resumable
by file existence and the report can be regenerated without the runs.

## The endpoints, in order of how much noise stands between them and the
## thing under test

1. `gp_hpwl_final`, `gp_iterations` -- from `3_3_place_gp.log`. What
   global placement optimizes, and how long it took in a unit that does
   not depend on machine load. One step from the change.
2. `wirelength` at global route.
3. `min_period_wns = clk_period - WNS` at global route, in the SDC's own
   units. Four stages and a resizer downstream of the change, so it
   carries the most noise; reported in picoseconds, never as a
   percentage of WNS.

Congestion is carried too (`grt_overflow`, `drc`). OpenROAD #7581 was a
routing-congestion failure traced to a placement change, so a study of
this knob that reported only timing could miss its most likely effect.

## The witness

Every record carries `arm_witnessed`, read back out of the log, next to
the `arm` the campaign asked for. They are compared in the report and a
disagreeing sample is dropped. Without it, a mode flag that never
reached the command line produces a clean run that reads as "this
distribution behaves exactly like the default" -- the one failure mode
that yields a plausible number instead of an error.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys

import gpl_progress
import grt_congestion
import initial_place

# ORFS's own per-step runtime line. Recorded always; quoted only for
# samples the campaign ran serially, because a several-wide sample's
# wall time is a property of the machine, not of the arm.
# GNU time's format, which ORFS annotates in the log as `[h:]min:sec` --
# the hours field is optional, so the last two fields are always minutes
# and seconds. Reading the first field as hours (which is what this
# regex did before, inherited from PR #977's harness) inflates every
# non-zero value 60-fold: `2:07.21` is 2 min 7.21 s, not 2 h 7.21 s. It
# also failed to match the three-field form at all, so a step that ran
# over an hour silently recorded no runtime rather than a wrong one.
_ELAPSED = re.compile(
    r"Elapsed time: (?:(?P<h>\d+):)?(?P<m>\d+):(?P<s>[0-9.]+)\[h:\]min:sec"
)

PLACE_STEPS = [
    "3_1_place_gp_skip_io",
    "3_2_place_iop",
    "3_3_place_gp",
    "3_4_place_resized",
    "3_5_place_dp",
]

TAIL_STEPS = PLACE_STEPS + ["4_1_cts", "5_1_grt"]

# Hashed as the witness that two runs did or did not do the same thing.
# The first answers "did the arm land", the last "did it still matter
# two stages later".
WITNESS_ODBS = ["3_1_place_gp_skip_io.odb", "3_3_place_gp.odb", "5_1_grt.odb"]


def sha1(path):
    """First 20 hex digits of a file's SHA-1, or None if absent.

    Args:
        path: the file.

    Returns:
        The prefix, matching the width ORFS prints in its own stage
        summary so the two can be compared by eye.
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
        Seconds, or None when the line is absent -- a step that failed
        before printing it.
    """
    match = _ELAPSED.search(text)
    if not match:
        return None
    return (
        int(match.group("h") or 0) * 3600
        + int(match.group("m")) * 60
        + float(match.group("s"))
    )


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
        try:
            with open(path) as handle:
                metrics[step] = json.load(handle)
        except (OSError, ValueError):
            # A truncated JSON is a failed step, not a crash here: the
            # record should say the step is missing, not refuse to exist.
            continue
    return metrics


def _read(path):
    if not os.path.exists(path):
        return None
    with open(path, errors="replace") as handle:
        return handle.read()


def harvest(logs_dir, results_dir, clk_period, **identity):
    """One sample record.

    Args:
        logs_dir: the run's `logs/<platform>/<design>/<variant>`.
        results_dir: its `results/<platform>/<design>/<variant>`.
        clk_period: the design's clock period, in the SDC's units, or
            None when the sample stopped before global route and the
            timing endpoint does not apply.
        **identity: platform, design, arm, seed and anything else the
            campaign wants carried into the tables.

    Returns:
        The record. Missing pieces are None and stay visible as such: a
        sample that did not reach grt still harvests its place-stage
        endpoints, which is what makes a partly-failed arm reportable
        rather than invisible.
    """
    metrics = read_metrics(logs_dir)
    grt = metrics.get("5_1_grt", {})
    place = metrics.get("3_5_place_dp", {})

    setup_ws = grt.get("globalroute__timing__setup__ws")
    record = dict(identity)
    record.update(
        {
            "clk_period": clk_period,
            "min_period_wns": (
                clk_period - setup_ws
                if clk_period is not None and setup_ws is not None
                else None
            ),
            "setup_ws": setup_ws,
            "setup_tns": grt.get("globalroute__timing__setup__tns"),
            "hold_ws": grt.get("globalroute__timing__hold__ws"),
            "wirelength": grt.get("globalroute__global_route__wirelength"),
            "drc": grt.get("globalroute__design__violations"),
            "place_area": place.get("detailedplace__design__instance__area"),
            "place_instances": place.get(
                "detailedplace__design__instance__count__stdcell"
            ),
        }
    )

    place_log = _read(os.path.join(logs_dir, "3_3_place_gp.log"))
    skip_io_log = _read(os.path.join(logs_dir, "3_1_place_gp_skip_io.log"))

    progress = gpl_progress.summarize(place_log) if place_log else None
    record["gp_hpwl_final"] = progress["hpwl_final"] if progress else None
    record["gp_iterations"] = progress["iterations"] if progress else None
    record["gp_segments"] = progress["segments"] if progress else None
    record["diverge_revert"] = progress["diverge_revert"] if progress else None
    record["gp_progress"] = progress

    record["initial_place"] = (
        initial_place.convergence(place_log) if place_log else None
    )
    record["initial_place_skip_io"] = (
        initial_place.convergence(skip_io_log) if skip_io_log else None
    )
    record["position_sources"] = (
        initial_place.position_sources(place_log) if place_log else None
    )
    record["position_sources_skip_io"] = (
        initial_place.position_sources(skip_io_log) if skip_io_log else None
    )
    record["mode_witness"] = (
        initial_place.mode_witness(place_log) if place_log else None
    )
    record["arm_witnessed"] = (
        initial_place.witnessed_arm(place_log) if place_log else None
    )

    # Congestion lives only in the log: ORFS writes 82 globalroute__*
    # metrics and not one of them is a congestion number. See
    # grt_congestion.py for why this study refuses to drop the endpoint.
    grt_log = _read(os.path.join(logs_dir, "5_1_grt.log"))
    congestion = grt_congestion.summarize(grt_log) if grt_log else None
    record["congestion"] = congestion
    record["grt_usage_pct"] = congestion["total_usage_pct"] if congestion else None
    record["grt_overflow"] = congestion["total_overflow"] if congestion else None
    record["grt_max_layer_usage_pct"] = (
        congestion["max_layer_usage_pct"] if congestion else None
    )
    record["grt_congested"] = congestion["congested"] if congestion else None

    runtimes = {}
    for step in TAIL_STEPS:
        text = _read(os.path.join(logs_dir, "%s.log" % step))
        if text is not None:
            runtimes[step] = elapsed_seconds(text)
    record["runtime_s"] = runtimes
    record["gp_wall_s"] = runtimes.get("3_3_place_gp")

    record["witness"] = {
        name: sha1(os.path.join(results_dir, name)) for name in WITNESS_ODBS
    }
    record["metrics"] = metrics
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--clk-period", type=float, default=None)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--design", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--arm", required=True)
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
        "%s/%s %s seed %d: hpwl %s iters %s witness %s"
        % (
            args.platform,
            args.design,
            args.arm,
            args.seed,
            record["gp_hpwl_final"],
            record["gp_iterations"],
            record["arm_witnessed"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
