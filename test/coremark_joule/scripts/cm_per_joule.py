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

The boundary travels with the number for the same reason. Once one point
hardens its L1 and another does not, a single study-wide statement about
what was measured is false for half the table -- so each point says what
its own hardened block contained.

The frequency is the one the power was computed at, which is the SDC
period the SAIF was timed against. It is deliberately not the achieved
maximum: those differ whenever WNS is positive, and reporting one while
having measured the other is how a screening number turns into a
performance claim it cannot support.
"""

import argparse
import json
import re
import sys


def totals(power_json):
    """Total power in watts from a report_power JSON."""
    return power_groups(power_json)["total"]


def power_groups(power_json):
    """Total power and its split from a report_power JSON, in watts.

    `dynamic` is internal plus switching. §5.7 is why the split travels
    with the point: dynamic energy per iteration is frequency-independent
    and leakage energy per iteration is not, so a total alone hides the
    term that moves with the operating point.
    """
    with open(power_json) as f:
        d = json.load(f)
    if "Total" not in d or not isinstance(d["Total"], dict):
        raise ValueError("{}: no Total group".format(power_json))
    t = d["Total"]
    out = {"total": t["total"]}
    if all(k in t for k in ("internal", "switching", "leakage")):
        out["internal"] = t["internal"]
        out["switching"] = t["switching"]
        out["leakage"] = t["leakage"]
        out["dynamic"] = t["internal"] + t["switching"]
    if "Macro" in d and isinstance(d["Macro"], dict):
        out["macro"] = d["Macro"]["total"]
    # §4.7's table: the total of every cell-kind group report_power
    # prints, so the split travels with the point and renders from it.
    out["groups"] = {
        k: v["total"]
        for k, v in d.items()
        if k not in ("Total", "Pad") and isinstance(v, dict) and "total" in v
    }
    return out


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


_CLK_PERIOD = re.compile(r"^\s*set\s+clk_period\s+(\d+)\s*$", re.M)


def frequency_mhz_from_sdc(sdc_text):
    """MHz from a constraints.sdc's `set clk_period <ps>`.

    One source for the period the design is built at and the frequency
    its energy is reported at. auto_period pins the former; this makes
    the latter follow rather than be maintained alongside it.
    """
    m = _CLK_PERIOD.search(sdc_text)
    if not m:
        raise SystemExit("no `set clk_period <ps>` line in the constraints")
    return 1.0e6 / float(m.group(1))


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
    freq = parser.add_mutually_exclusive_group(required=True)
    freq.add_argument("--frequency-mhz", type=float)
    freq.add_argument(
        "--frequency-from-sdc",
        help="the design's constraints.sdc, read for `set clk_period <ps>`. "
        "Preferred over --frequency-mhz: the reported frequency and the "
        "period the design was built at are then one fact rather than two "
        "declarations free to drift, which is how this study came to "
        "report ibex at a frequency its netlist missed by 74 ps.",
    )
    parser.add_argument("--core", required=True)
    parser.add_argument("--isa", required=True)
    parser.add_argument("--stage", default="grt")
    parser.add_argument(
        "--boundary",
        required=True,
        help="what the hardened block contains. The study's rule is the "
        "core and its L1, or the small SRAM that stands in for one "
        "(§3.1); a point that hardens no memory does not meet it, and "
        "says so here rather than in a footnote that applies to every "
        "point equally.",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])

    with open(args.per_mhz) as f:
        perf = json.load(f)

    groups = power_groups(args.power)
    power_w = groups["total"]
    f_mhz = args.frequency_mhz
    if f_mhz is None:
        with open(args.frequency_from_sdc) as f:
            f_mhz = frequency_mhz_from_sdc(f.read())
    result = combine(perf["coremark_per_mhz"], f_mhz, power_w)
    result.update(
        {
            "core": args.core,
            "isa": args.isa,
            "stage": args.stage,
            "boundary": args.boundary,
            "cycles_per_iteration": perf["cycles_per_iteration"],
            "build_flags": perf.get("build_flags"),
            "activity": "saif",
        }
    )
    if "dynamic" in groups:
        result["dynamic_power_w"] = groups["dynamic"]
        result["leakage_power_w"] = groups["leakage"]
    if "macro" in groups:
        result["macro_power_w"] = groups["macro"]
    if groups.get("groups"):
        result["power_groups_w"] = groups["groups"]

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
