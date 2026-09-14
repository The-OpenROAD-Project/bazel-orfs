#!/usr/bin/env python3
"""Write every measured point into results.json, in the source tree.

The measurements are expensive -- a gate-level CoreMark run is minutes
per core -- and the presentation is not. Iterating on a plot should not
re-run a flow, so the numbers are pinned into a committed file and the
plot reads only that. Same split as the floorplan derivation: bazel
caches the deriving, a `run` target writes the result where a human can
read it in a diff, and nothing downstream needs the flow at all.

It also makes the data reviewable. A number that changes shows up as a
line in a pull request, next to the commit that changed it, rather than
living in an output directory nobody keeps.

Usage (via the generated target):
    bazelisk run //test/coremark_joule:pin
"""

import argparse
import json
import os
import sys

# Where the pinned file lives, relative to the workspace root. bazel run
# sets BUILD_WORKSPACE_DIRECTORY to the source tree, which is the only
# place writing is meaningful -- the runfiles copy is read-only and
# discarded.
RESULTS = "test/coremark_joule/results.json"


def load_points(paths):
    points = []
    for path in paths:
        with open(path) as f:
            points.append(json.load(f))
    return sorted(points, key=lambda p: (p["core"], p["isa"]))


def load_pending(paths):
    """Configurations with an x-coordinate but no y, and why.

    A core whose CoreMark/MHz is measured but whose energy is not is not
    absent from the study -- it is half-done. Dropping it from the pinned
    file would leave the plot quietly showing fewer cores than the study
    has, which is the failure the report format exists to avoid.
    """
    pending = []
    for entry in paths:
        path, core, isa, reason = entry.split(":", 3)
        with open(path) as f:
            perf = json.load(f)
        pending.append(
            {
                "core": core,
                "isa": isa,
                "coremark_per_mhz": perf["coremark_per_mhz"],
                "cycles_per_iteration": perf["cycles_per_iteration"],
                "coremark_per_joule": None,
                "blocked_on": reason,
            }
        )
    return sorted(pending, key=lambda p: (p["core"], p["isa"]))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("points", nargs="+", help="per-point JSON files")
    parser.add_argument(
        "--pending",
        action="append",
        default=[],
        metavar="JSON:CORE:ISA:REASON",
        help="a measured CoreMark/MHz whose energy is not measured yet, "
        "with what it is waiting on",
    )
    args = parser.parse_args(argv[1:])

    root = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not root:
        print(
            "pin_results: no BUILD_WORKSPACE_DIRECTORY; run this through "
            "`bazelisk run`, which is what points it at the source tree",
            file=sys.stderr,
        )
        return 1

    points = load_points(args.points)
    pending = load_pending(args.pending)
    out = os.path.join(root, RESULTS)

    previous = None
    if os.path.exists(out):
        with open(out) as f:
            previous = json.load(f)

    document = {
        # Stated rather than implied: every number here is comparable to
        # the others only because these are the same for all of them.
        "provenance": {
            "platform": "asap7",
            "stage": "grt",
            "activity": "saif, one hot CoreMark iteration",
            "frequency": "the SDC period the SAIF was timed against, "
            "not an achieved maximum",
            "note": "Not reportable CoreMark scores: a three-iteration run "
            "does not satisfy CoreMark's run rules.",
        },
        "points": points,
        # Half-done configurations, carried so the plot cannot show
        # fewer cores than the study has without saying so.
        "pending": pending,
    }

    with open(out, "w") as f:
        json.dump(document, f, indent=2, sort_keys=True)
        f.write("\n")

    if previous == document:
        print("pin_results: {} unchanged".format(RESULTS))
    else:
        print("pin_results: wrote {} point(s) to {}".format(len(points), RESULTS))
        for p in points:
            print(
                "  {:9s} {:8s} {:9.4f} CoreMark/MHz  {:7.2f} mW  "
                "{:>9,.0f} CoreMark/J".format(
                    p["core"],
                    p["isa"],
                    p["coremark_per_mhz"],
                    p["power_w"] * 1e3,
                    p["coremark_per_joule"],
                )
            )
        for p in pending:
            print(
                "  {:9s} {:8s} {:9.4f} CoreMark/MHz   energy not yet "
                "measured: {}".format(
                    p["core"], p["isa"], p["coremark_per_mhz"], p["blocked_on"]
                )
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
