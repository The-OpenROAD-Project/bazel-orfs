#!/usr/bin/env python3
"""Core-only energy per CoreMark iteration, per arm, beside the published rows.

§4.8 of the paper found that ibex's core-only energy per iteration at
global route on ASAP7 equals a published post-synthesis figure for the
same core in TSMC 65 nm, which node scaling says should not happen. This
renders the arms that split that disagreement -- the same core at the
same stage and periods as the published rows -- into one table.

Core-only is the report_power total minus its Macro group: the two
program memories are inside the tile but outside the published boundary.
Energy per iteration is power times the iteration's duration,
cycles_per_iteration times the SDC period, the period the SAIF was timed
against (see coremark_saif's clk_period_ps).
"""

import argparse
import json
import sys

# The published rows this is set beside, from Gallmann et al., CARRV 2021,
# Table 5, default ibex config: TSMC 65 nm, 1.2 V typical, post-synthesis
# netlist, PrimeTime on post-synthesis simulation activity. Dynamic
# energy per CoreMark iteration in microjoules and leakage in nanojoules,
# at the frequency each netlist was synthesised for.
PUBLISHED = [
    {
        "label": "[15] synth, 100 MHz",
        "f_mhz": 100.0,
        "dyn_uj": 3.40,
        "leak_nj": 0.75,
        "cm_per_mhz": 2.36,
    },
    {
        "label": "[15] synth, 500 MHz",
        "f_mhz": 500.0,
        "dyn_uj": 0.92,
        "leak_nj": 5.54,
        "cm_per_mhz": 2.36,
    },
]

GROUPS = ["Sequential", "Combinational", "Clock", "Macro", "Pad", "Total"]


def group(report, name, field):
    g = report.get(name)
    if not isinstance(g, dict) or g.get(field) is None:
        return 0.0
    return float(g[field])


def arm_row(label, period_ps, report, cycles_per_iteration):
    """One arm: core-only power split and energy per iteration."""
    seconds = cycles_per_iteration * period_ps * 1e-12
    total = group(report, "Total", "total")
    macro = group(report, "Macro", "total")
    core = total - macro
    core_leak = group(report, "Total", "leakage") - group(report, "Macro", "leakage")
    core_dyn = core - core_leak
    return {
        "label": label,
        "period_ps": period_ps,
        "f_mhz": 1e6 / period_ps,
        "total_w": total,
        "macro_w": macro,
        "core_w": core,
        "core_dyn_w": core_dyn,
        "core_leak_w": core_leak,
        "clock_w": group(report, "Clock", "total"),
        "core_dyn_uj": core_dyn * seconds * 1e6,
        "core_leak_nj": core_leak * seconds * 1e9,
        "core_uj": core * seconds * 1e6,
    }


def render(rows, cycles_per_iteration, cm_per_mhz):
    out = [
        "| arm | f | core-only P | of which clock | core-only dynamic / iteration | leakage / iteration | CoreMark/MHz |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            "| {label} | {f:.0f} MHz | {core:.2f} mW | {clk:.2f} mW | **{dyn:.2f} µJ** | {leak:.2f} nJ | {cm:.2f} |".format(
                label=r["label"],
                f=r["f_mhz"],
                core=r["core_w"] * 1e3,
                clk=r["clock_w"] * 1e3,
                dyn=r["core_dyn_uj"],
                leak=r["core_leak_nj"],
                cm=cm_per_mhz,
            )
        )
    for p in PUBLISHED:
        out.append(
            "| {label} | {f:.0f} MHz | — | none | **{dyn:.2f} µJ** | {leak:.2f} nJ | {cm:.2f} |".format(
                **{
                    "label": p["label"],
                    "f": p["f_mhz"],
                    "dyn": p["dyn_uj"],
                    "leak": p["leak_nj"],
                    "cm": p["cm_per_mhz"],
                }
            )
        )
    out.append("")
    out.append(
        "Core-only is report_power's Total minus its Macro group. One iteration is "
        "{:,} cycles; energy is power times cycles times the SDC period.".format(
            cycles_per_iteration
        )
    )
    return "\n".join(out) + "\n"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-mhz", required=True)
    parser.add_argument(
        "--arm", action="append", default=[], metavar="LABEL:PERIOD_PS:JSON"
    )
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args(argv[1:])

    with open(args.per_mhz) as f:
        perf = json.load(f)
    cycles = int(perf["cycles_per_iteration"])
    rows = []
    for spec in args.arm:
        label, period, path = spec.rsplit(":", 2)
        with open(path) as f:
            report = json.load(f)
        rows.append(arm_row(label, int(period), report, cycles))
    rows.sort(key=lambda r: (-r["f_mhz"], r["label"]))
    with open(args.out_md, "w") as f:
        f.write(render(rows, cycles, perf["coremark_per_mhz"]))
    with open(args.out_json, "w") as f:
        json.dump(
            {"cycles_per_iteration": cycles, "arms": rows, "published": PUBLISHED},
            f,
            indent=2,
        )
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
