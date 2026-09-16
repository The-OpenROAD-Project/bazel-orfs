#!/usr/bin/env python3
"""How much could OpenSTA's activity estimate move the answer?

The pin audit says which pins were measured. This says whether the ones
that were not could matter, and it answers with a number rather than an
argument.

`set_power_activity -input` is the only knob through which a density
OpenSTA invented enters the design: it seeds every levelization root --
top-level input ports and tie-cell outputs -- that carries no
annotation, and everything else is either annotated, propagated from
those roots, or taken exactly from the SDC clock. Sweeping it from 0.0
(an unannotated root never toggles) to 2.0 (it toggles as often as the
clock) covers the whole range the estimate could plausibly take.

Two arms, because a flat line is only evidence if the knob works:

  vectorless  no SAIF. The total must move, and by how much is what
              calibrates the epsilon: it is the size of the answer the
              study would have reported had it not measured activity.
  saif        the SAIF read. The total must not move.

The pass condition is therefore a ratio between two measured spreads,
not a threshold pulled out of the air.
"""

import argparse
import json
import sys


def group_totals(power_json):
    """Internal, switching, leakage and total watts from a report_power JSON."""
    with open(power_json) as f:
        d = json.load(f)
    if "Total" not in d or not isinstance(d["Total"], dict):
        raise ValueError("{}: no Total group".format(power_json))
    total = d["Total"]
    return {
        "internal": total.get("internal"),
        "switching": total.get("switching"),
        "leakage": total.get("leakage"),
        "total": total["total"],
    }


def parse_point(spec):
    """`arm:activity:path`, as flow/activity_sweep.tcl was told to write it."""
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError("expected arm:activity:path, got {!r}".format(spec))
    return parts[0], float(parts[1]), parts[2]


def spread(values):
    """Peak-to-peak as a fraction of the mean.

    Relative, because the two arms are the same design at the same stage
    and what is being compared is how much each moved, not how big each
    was.
    """
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0.0:
        return 0.0
    return (max(values) - min(values)) / mean


def evaluate(points, epsilon, min_control_spread):
    arms = {}
    for arm, activity, path in points:
        arms.setdefault(arm, []).append((activity, group_totals(path)))

    result = {"epsilon": epsilon, "min_control_spread": min_control_spread, "arms": {}}
    for arm in sorted(arms):
        rows = sorted(arms[arm])
        totals = [groups["total"] for _, groups in rows]
        result["arms"][arm] = {
            "points": [
                {"activity": activity, "power_w": groups["total"], "groups": groups}
                for activity, groups in rows
            ],
            "spread": spread(totals),
            "min_w": min(totals),
            "max_w": max(totals),
        }

    failures = []
    saif = result["arms"].get("saif")
    control = result["arms"].get("vectorless")

    if saif is None:
        failures.append("no saif arm: nothing was measured")
    elif saif["spread"] > epsilon:
        failures.append(
            "the SAIF-driven total moves {:.4%} across the sweep, over the "
            "{:.4%} budget: pins OpenSTA estimated are contributing".format(
                saif["spread"], epsilon
            )
        )

    if control is None:
        failures.append("no vectorless arm: the sweep has no positive control")
    elif control["spread"] < min_control_spread:
        failures.append(
            "the vectorless total moves only {:.4%} across the sweep, under "
            "the {:.4%} floor: the knob this test turns is not doing "
            "anything, so a flat SAIF arm would prove nothing".format(
                control["spread"], min_control_spread
            )
        )

    result["failures"] = failures
    result["verdict"] = "fail" if failures else "pass"
    if saif and control and saif["spread"] > 0.0:
        result["control_ratio"] = control["spread"] / saif["spread"]
    return result


def report(result, out=sys.stdout):
    for arm in sorted(result["arms"]):
        data = result["arms"][arm]
        out.write("{}:\n".format(arm))
        for point in data["points"]:
            out.write(
                "  activity {:>4}  {:.6e} W\n".format(
                    point["activity"], point["power_w"]
                )
            )
        out.write("  spread {:.4%}\n".format(data["spread"]))
    for failure in result["failures"]:
        out.write("FAIL: {}\n".format(failure))
    out.write("verdict {}\n".format(result["verdict"]))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--point",
        action="append",
        required=True,
        metavar="ARM:ACTIVITY:PATH",
        help="one report_power JSON and the sweep point that produced it",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=0.005,
        help="how much the SAIF-driven total may move across the whole "
        "sweep, as a fraction of its mean",
    )
    parser.add_argument(
        "--min-control-spread",
        type=float,
        default=0.05,
        help="how much the vectorless total must move for the sweep to "
        "count as a working positive control",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])

    points = [parse_point(spec) for spec in args.point]
    result = evaluate(points, args.epsilon, args.min_control_spread)

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")

    report(result)
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
