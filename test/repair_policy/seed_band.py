#!/usr/bin/env python3
"""The wall band under an equivalent netlist: the default with other placement seeds.

A policy that changes what repair_timing does changes the netlist, and
a different netlist changes what detailed route costs by more than the
flow's run-to-run spread on identical inputs (1-2 s). The fair band for
the wall axis is therefore the spread the default itself shows under an
innocuous perturbation: the same flow with GPL_RANDOM_SEED 2 and 3
(seed 1 is the unseeded draw). This reads those arms beside the default
and writes, per design, the range of the flow wall and of each KPI the
verdict judges, so verdict.py can treat a wall move inside that range as
a tie the way it treats a KPI move inside the history band.

    seed_band.py --results DIR --out bands.json [--base base-p00670068] \\
                 [--seeds base-p00670068s2 base-p00670068s3]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "repair_timing_runtime"))
import verdict  # noqa: E402

STAGES = ("4_1_cts", "5_1_grt", "5_2_route")


def spread(values):
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    return max(values) - min(values)


def bands(results_dir, base_arm, seed_arms, hist_bands):
    arms = [verdict.load_arm(results_dir, a) for a in [base_arm] + seed_arms]
    out = {}
    for design in sorted(arms[0]):
        records = [a.get(design) for a in arms if a.get(design)]
        if len(records) < 2:
            continue
        walls = [verdict.flow_wall(r) for r in records]
        ks = [verdict.kpis(r, hist_bands) for r in records]
        entry = {
            "runs": len(records),
            "flow_wall_s": walls,
            "flow_wall_band_s": spread(walls),
            "stage_wall_band_s": {
                s: spread([(r["substeps"].get(s) or {}).get("wall_s") for r in records])
                for s in STAGES
            },
        }
        for key, _, label in verdict.KPI_AXES:
            entry[key] = spread([k.get(key) for k in ks])
        out[design] = entry
    return out


def table(b):
    lines = [
        "| design | runs | flow wall (s), default then seeds | wall band (s) | cts | grt | route | min period band (ps) | TNS band | area band | wire band |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for design, e in sorted(b.items()):
        sw = e["stage_wall_band_s"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                design,
                e["runs"],
                " / ".join("{:.0f}".format(w) for w in e["flow_wall_s"]),
                verdict.fmt(e["flow_wall_band_s"], 0),
                verdict.fmt(sw.get("4_1_cts"), 0),
                verdict.fmt(sw.get("5_1_grt"), 0),
                verdict.fmt(sw.get("5_2_route"), 0),
                verdict.fmt(e.get("min_period"), 1),
                verdict.fmt(e.get("finish__timing__setup__tns"), 1),
                verdict.fmt(e.get("finish__design__instance__area"), 1),
                verdict.fmt(e.get("detailedroute__route__wirelength"), 0),
            )
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--base", default="base-p00670068")
    parser.add_argument("--seeds", nargs="+", default=["base-p00670068s2", "base-p00670068s3"])
    parser.add_argument("--bands", help="history noise bands, for the clock period fallback")
    parser.add_argument("--out", help="write the bands as JSON here")
    args = parser.parse_args()
    hist = {}
    if args.bands:
        with open(args.bands) as handle:
            hist = json.load(handle)
    b = bands(args.results, args.base, args.seeds, hist)
    if not b:
        raise SystemExit("no design has the default and a seed arm in {}".format(args.results))
    sys.stdout.write(table(b))
    if args.out:
        with open(args.out, "w") as handle:
            json.dump(b, handle, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
