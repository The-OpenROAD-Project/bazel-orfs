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
import re
import math
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
    dict(
        _CF25_PROVENANCE,
        **{
            "name": "CVA6",
            "coremark_per_mhz": 2.19,
            "frequency_mhz": 900.0,
            "power_w": 0.06988,
            "coremark_per_joule": 2.19 * 900.0 / 0.06988,
        }
    ),
    dict(
        _CF25_PROVENANCE,
        **{
            "name": "CVA6S+",
            "coremark_per_mhz": 2.84,
            "frequency_mhz": 900.0,
            "power_w": 0.09429,
            "coremark_per_joule": 2.84 * 900.0 / 0.09429,
        }
    ),
    dict(
        _CF25_PROVENANCE,
        **{
            "name": "XuanTie C910",
            "coremark_per_mhz": 4.86,
            "frequency_mhz": 1300.0,
            "power_w": 0.21481,
            "coremark_per_joule": 4.86 * 1300.0 / 0.21481,
        }
    ),
]

# The claim on the README's title page, and what it was checked against.
# Update `as_of` when the check is redone; §4.5 of the README is the
# human-readable form.
UNIQUENESS = {
    "as_of": "2026-09",
    "as_of_text": "September 2026",
    "claim": "the only comparison of CoreMark/Joule across more than one hardened core, with activity from CoreMark itself, from an open and re-runnable flow",
    "qualifiers": [
        "more than one core, each hardened to a netlist",
        "switching activity from CoreMark itself, not an estimator",
        "every input open and pinned; re-runnable with one command",
    ],
    "near_misses": [
        "Schiavone et al., PATMOS 2017: 3 cores, CoreMark energy, PrimeTime, UMC 65 nm -- not re-runnable",
        "Gallmann et al., CARRV 2021: ibex and CV32E40P, CoreMark energy, PrimeTime, TSMC 65 nm -- not re-runnable",
        "Djupdal et al., arXiv 2502.06588: 7 cores, MachSuite not CoreMark, commercial 130 nm -- wrong workload, not re-runnable",
        "Fu et al., CF'25: 3 cores, power on matmult-int not CoreMark, GF 22 FDX -- wrong workload, not re-runnable",
        "Elsadek and Tawfik, IEEE 2021: 7 cores on an FPGA -- not hardened",
        "EEMBC ULPMark-CM: one silicon MCU per score -- not a comparison on one flow",
    ],
}

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


def two_sigma(values):
    """Twice the sample standard deviation; zero for a single value.

    §5.13: the spread is reported as 2σ, and the resolvable difference at
    k runs per arm is 2σ·sqrt(2/k). A single run's 2σ is zero, which is
    honest -- it says nothing has been measured about the spread.
    """
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return 2.0 * math.sqrt(var)


def seed_label(path):
    """The seed a sample file was run at, from its `_seedN` name; else its stem."""
    m = re.search(r"_seed(\d+)", os.path.basename(path))
    return m.group(1) if m else os.path.splitext(os.path.basename(path))[0]


def attach_samples(points, sample_paths):
    """Fold placement-seed samples into the point they belong to.

    Each sample is a point JSON from a seed variant of the same core
    (§5.13). The pinned point stays the design's own draw -- seed 1, the
    one every audit and sweep in the paper was run on -- and carries the
    ensemble beside it: every sample's power and CoreMark/Joule, the
    seed count, and 2σ of each, so a difference between two points can be
    read against the spread that would swallow it.
    """
    by_core = {(p["core"], p["isa"]): p for p in points}
    for path in sample_paths:
        with open(path) as f:
            sample = json.load(f)
        key = (sample["core"], sample["isa"])
        if key not in by_core:
            raise SystemExit(
                "pin_results: sample {} names a core with no point".format(path)
            )
        by_core[key].setdefault("seed_samples", []).append(
            {
                "seed": seed_label(path),
                "power_w": sample["power_w"],
                "coremark_per_joule": sample["coremark_per_joule"],
                "dynamic_power_w": sample.get("dynamic_power_w"),
                "leakage_power_w": sample.get("leakage_power_w"),
            }
        )
    for p in points:
        samples = [
            {
                "seed": "own",
                "power_w": p["power_w"],
                "coremark_per_joule": p["coremark_per_joule"],
                "dynamic_power_w": p.get("dynamic_power_w"),
                "leakage_power_w": p.get("leakage_power_w"),
            }
        ] + p.pop("seed_samples", [])
        if len(samples) > 1:
            p["seeds"] = len(samples)
            p["seed_samples"] = samples
            p["power_2sigma_w"] = two_sigma([x["power_w"] for x in samples])
            p["coremark_per_joule_2sigma"] = two_sigma(
                [x["coremark_per_joule"] for x in samples]
            )
    return points


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
        "--sample",
        action="append",
        default=[],
        metavar="JSON",
        help="a seed variant's point JSON, folded into the matching core's "
        "point as one sample of its placement-seed ensemble (§5.13)",
    )
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

    points = attach_samples(load_points(args.points), args.sample)
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
            "parasitics": "estimate_parasitics -global_routing; no " "extracted SPEF",
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
            # The title page's claim is about the literature on a day.
            # The date lives here so the README's first line is rendered
            # and checked against it (readme_numbers_test), and so a
            # re-pin cannot silently outlive the search that justifies it.
            "uniqueness": UNIQUENESS,
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
                "{:>9,.0f} CoreMark/J{}".format(
                    p["core"],
                    p["isa"],
                    p["coremark_per_mhz"],
                    p["power_w"] * 1e3,
                    p["coremark_per_joule"],
                    (
                        "  ±{:,.0f} (2σ, {} seeds)".format(
                            p["coremark_per_joule_2sigma"], p["seeds"]
                        )
                        if "seeds" in p
                        else ""
                    ),
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
