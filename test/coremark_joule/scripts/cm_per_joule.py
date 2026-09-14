#!/usr/bin/env python3
"""Combine performance, frequency and power into CoreMark/Joule.

    CoreMark score  = CoreMark/MHz * f_MHz
    CoreMark/Joule  = score / power_W

Both axes of the study's plot come from here, and the arithmetic is
trivial; what the file is really for is keeping the provenance attached
to the number. A CoreMark/Joule is only comparable to another one if the
frequency it was taken at, the stage it was measured at, and whether the
activity was measured or assumed are all the same -- so those travel with
it rather than living in whoever's memory produced the plot.

The frequency is the one the power was computed at, which is the SDC
period the SAIF was timed against. It is deliberately not the achieved
maximum: those differ whenever WNS is positive, and reporting one while
having measured the other is how a screening number turns into a
performance claim it cannot support.
"""

import argparse
import json
import sys


def totals(power_json):
    """Total power in watts from a report_power JSON."""
    with open(power_json) as f:
        d = json.load(f)
    if "Total" in d and isinstance(d["Total"], dict):
        return d["Total"]["total"]
    raise ValueError("{}: no Total group".format(power_json))


def combine(coremark_per_mhz, f_mhz, power_w):
    score = coremark_per_mhz * f_mhz
    return {
        "coremark_per_mhz": coremark_per_mhz,
        "frequency_mhz": f_mhz,
        "power_w": power_w,
        "coremark_score": score,
        "coremark_per_joule": score / power_w,
        "joule_per_iteration": power_w / score,
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-mhz", required=True, help="the *_per_mhz.json")
    parser.add_argument("--power", required=True, help="the SAIF-driven power JSON")
    parser.add_argument(
        "--vectorless-power",
        help="the clock-only power JSON. When given, it is recorded and "
        "checked: a SAIF that failed to bind leaves the two identical, and "
        "OpenSTA reports that as a number rather than as an error.",
    )
    parser.add_argument("--frequency-mhz", type=float, required=True)
    parser.add_argument("--core", required=True)
    parser.add_argument("--isa", required=True)
    parser.add_argument("--stage", default="grt")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])

    with open(args.per_mhz) as f:
        perf = json.load(f)

    power_w = totals(args.power)
    result = combine(perf["coremark_per_mhz"], args.frequency_mhz, power_w)
    result.update(
        {
            "core": args.core,
            "isa": args.isa,
            "stage": args.stage,
            "cycles_per_iteration": perf["cycles_per_iteration"],
            "build_flags": perf.get("build_flags"),
            "activity": "saif",
        }
    )

    if args.vectorless_power:
        vectorless = totals(args.vectorless_power)
        result["vectorless_power_w"] = vectorless
        if vectorless == power_w:
            print(
                "cm_per_joule: the SAIF-driven and vectorless power are "
                "identical ({} W). The SAIF did not bind -- OpenSTA falls "
                "back to default activity rather than failing -- so this is "
                "not a measured number.".format(power_w),
                file=sys.stderr,
            )
            return 1

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    print(
        "{} {}: {:.0f} CoreMark/J  ({:.4f} CoreMark/MHz at {:.0f} MHz, "
        "{:.2f} mW)".format(
            args.core,
            args.isa,
            result["coremark_per_joule"],
            result["coremark_per_mhz"],
            result["frequency_mhz"],
            power_w * 1e3,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
