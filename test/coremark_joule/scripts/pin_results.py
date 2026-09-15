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

# A second series from the literature: cores implemented in
# GlobalFoundries 22 FDX, drawn as its own series because it is not
# like-for-like with the asap7 points -- different process, different
# tools, different stage, different corner, and a boundary the source
# does not state.
#
# CoreMark/Joule is *derived* from the paper's own figures:
#   score = CoreMark/MHz * f,  CoreMark/Joule = score / power
# with power taken near each core's maximum frequency (Figure 7) and
# CoreMark/MHz from its Table. Nothing is scaled between nodes.
#
# Two things the derivation carries that are worth stating where the
# numbers live rather than only in the paper:
#
# - The boundary is not stated by the source. The cores are configured
#   with 64 KB two-way L1 I and D caches, but Figure 7's breakdown names
#   Fetch, Decode, Issue, Integer Execution, Load/Store Unit, Floating
#   Point and Control Flow, and no cache term appears in it. Whether the
#   reported core power includes the L1s cannot be determined from the
#   paper, so it is recorded here as unstated rather than assumed.
# - The power is measured on matmult-int, not on CoreMark. The paper
#   states its power numbers for that benchmark. So a derived
#   CoreMark/Joule combines a CoreMark performance number with a
#   matmult-int power number, and is an estimate of the paper's energy
#   efficiency rather than a figure the paper reports.
_CF25 = "Ramping Up Open-Source RISC-V Cores, ACM CF'25 (arXiv:2505.24363)"

# What every entry in LITERATURE shares, so a reader of results.json
# does not have to find the paper to know what the number is.
_CF25_PROVENANCE = {
    "process": "GF 22 FDX",
    "boundary": "not stated by the source; 64 KB two-way L1 I/D configured, "
    "but Figure 7's breakdown names only pipeline units",
    "power_benchmark": "matmult-int (not CoreMark)",
    "corner": "0.8 V, TT, 25 C, RC typical",
    "tool": "Synopsys PrimeTime 2022.03, post-layout netlist simulation",
    "derivation": "CoreMark/Joule = CoreMark/MHz * f / power, computed here",
    "source": _CF25,
}

LITERATURE = [
    dict(_CF25_PROVENANCE, **{
        "name": "CVA6",
        "coremark_per_mhz": 2.19,
        "frequency_mhz": 900.0,
        "power_w": 0.06988,
        "coremark_per_joule": 2.19 * 900.0 / 0.06988,
    }),
    dict(_CF25_PROVENANCE, **{
        "name": "CVA6S+",
        "coremark_per_mhz": 2.84,
        "frequency_mhz": 900.0,
        "power_w": 0.09429,
        "coremark_per_joule": 2.84 * 900.0 / 0.09429,
    }),
    dict(_CF25_PROVENANCE, **{
        "name": "XuanTie C910",
        "coremark_per_mhz": 4.86,
        "frequency_mhz": 1300.0,
        "power_w": 0.21481,
        "coremark_per_joule": 4.86 * 1300.0 / 0.21481,
    }),
]

# Published performance per clock with no energy figure at a stated
# boundary, so x-axis orientation only.
REFERENCES = [
    {
        "name": "SonicBOOM",
        "coremark_per_mhz": 6.2,
        "source": "SonicBOOM: The 3rd Generation Berkeley Out-of-Order Machine, CARRV 2020",
    },
]


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
            "corner": "BC: RVT, FF, 0.77 V, 25 C, NLDM -- asap7's ORFS "
            "default, which is the best case rather than the typical one",
            "parasitics": "estimate_parasitics -global_routing; no "
            "extracted SPEF",
            "activity": "saif, one hot CoreMark iteration",
            "activity_annotation": "100% of pins annotated from the SAIF "
            "on every point; see the *_activity_audit.json and "
            "*_activity_sweep_check.json targets",
            "simulation": "Verilator, two-state and zero-delay: carries no "
            "glitch power",
            # Short on purpose: it is rendered as a caption line under
            # the figure. What each point actually hardened is no longer
            # the same answer for all of them, so it travels per point
            # in that point's own `boundary` field.
            "boundary": "core + L1, or the small SRAM standing in for "
            "one -- stated per point",
            "frequency": "the SDC period the SAIF was timed against, "
            "not an achieved maximum",
            "note": "Not reportable CoreMark scores: a three-iteration run "
            "does not satisfy CoreMark's run rules.",
        },
        "points": points,
        # Published performance-per-clock for cores not measured here.
        # x-axis orientation only; see REFERENCES for why there is no y.
        "references": REFERENCES,
        "literature": LITERATURE,
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
