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


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("points", nargs="+", help="per-point JSON files")
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
    }

    with open(out, "w") as f:
        json.dump(document, f, indent=2, sort_keys=True)
        f.write("\n")

    if previous == document:
        print("pin_results: {} unchanged".format(RESULTS))
    else:
        print(
            "pin_results: wrote {} point(s) to {}".format(len(points), RESULTS)
        )
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
