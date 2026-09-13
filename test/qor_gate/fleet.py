#!/usr/bin/env python3

"""Combine per-design Pareto verdicts into one score for a pull request.

`check_pareto.py` answers "where did this design's point move". That is
the right question per design and the wrong one per PR, because a single
design cannot tell a signal from a draw. The study in #981 measured how
the two differ: across 105 commits that moved thresholds on five or more
ORFS designs at once, the median direction concordance was 98.4%, and of
the twelve that were pure OpenROAD submodule bumps, twelve of twelve were
100% concordant. A real tool change moves many designs the same way; a
draw moves one.

So this aggregates, and the rule it aggregates by is **two witnesses**.
An axis counts as moved only when at least `--witnesses` designs moved it
in the same direction. One design moving alone is reported, and reported
as unresolved -- never as a result.

The verdicts, in the vocabulary the study settled on:

  `not-applicable`  no design produced a comparable point
  `inert`           every design bit-identical to baseline. The strongest
                    statement available, and the cheapest: no draw was
                    taken, so no statistics are needed
  `better`          at least `witnesses` designs improved an axis, none
                    regressed one with the same support
  `worse`           the same, regressed
  `trade`           both, on different axes -- a move along the front, and
                    a legitimate outcome rather than a failure
  `did-not-resolve` something moved, but never with enough witnesses

`did-not-resolve` is NOT `inert` and must never render as a green check.
Conflating them is exactly how a real regression merges: the gate says
nothing, and nothing reads as fine.

Hard-constraint violations (DRC, placement, antenna) escalate on a single
witness, unlike every other axis. That asymmetry is earned rather than
assumed: in four years of ORFS history the hard-constraint metrics have a
residual of exactly zero, which is the control that shows they do not
drift on their own.
"""

import argparse
import json
import os
import sys

# Never a trade, and never a draw: one witness is enough.
HARD_VERDICTS = ("dominated",)

MOVED = ("better", "worse", "trade", "dominated")


def load(paths):
    """Read per-design verdicts, keyed by the design they came from."""
    out = {}
    for path in paths:
        name = os.path.basename(path)
        for suffix in (".pareto.json", ".json"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        with open(path) as fh:
            out[name] = json.load(fh)
    return out


def tally(verdicts):
    """Count, per axis, how many designs improved and regressed it."""
    improved, regressed = {}, {}
    for design, v in verdicts.items():
        for axis in v.get("improved", []):
            improved.setdefault(axis, []).append(design)
        for axis in v.get("regressed", []):
            regressed.setdefault(axis, []).append(design)
    return improved, regressed


def score(verdicts, witnesses=2, identical=()):
    """Reduce per-design verdicts to one fleet verdict."""
    if not verdicts:
        return {"verdict": "not-applicable", "reason": "no designs reported"}

    identical = set(identical)
    if identical and identical >= set(verdicts):
        return {
            "verdict": "inert",
            "reason": f"all {len(verdicts)} designs bit-identical to baseline",
            "designs": sorted(verdicts),
            "witnesses_required": witnesses,
        }

    hard = sorted(
        d for d, v in verdicts.items() if v.get("verdict") in HARD_VERDICTS
    )
    improved, regressed = tally(verdicts)

    strong_up = {a: ds for a, ds in improved.items() if len(ds) >= witnesses}
    strong_down = {a: ds for a, ds in regressed.items() if len(ds) >= witnesses}
    weak = sorted(
        set(a for a, ds in improved.items() if len(ds) < witnesses)
        | set(a for a, ds in regressed.items() if len(ds) < witnesses)
    )

    if hard:
        verdict = "worse"
        reason = (
            f"hard constraint violated on {', '.join(hard)} "
            "(never a trade; one witness is enough because these metrics "
            "do not drift)"
        )
    elif strong_up and strong_down:
        verdict = "trade"
        reason = (
            f"improved {', '.join(sorted(strong_up))}; "
            f"regressed {', '.join(sorted(strong_down))} "
            "-- a move along the front, not a regression"
        )
    elif strong_up:
        verdict = "better"
        reason = f"improved {', '.join(sorted(strong_up))} with support"
    elif strong_down:
        verdict = "worse"
        reason = f"regressed {', '.join(sorted(strong_down))} with support"
    elif weak:
        verdict = "did-not-resolve"
        reason = (
            f"movement on {', '.join(weak)} but fewer than {witnesses} "
            "designs agreed -- this is not evidence of no effect"
        )
    else:
        verdict = "did-not-resolve"
        reason = "every axis within its tie band on every design"

    return {
        "verdict": verdict,
        "reason": reason,
        "witnesses_required": witnesses,
        "designs": sorted(verdicts),
        "improved": {a: sorted(ds) for a, ds in sorted(improved.items())},
        "regressed": {a: sorted(ds) for a, ds in sorted(regressed.items())},
        "unsupported_axes": weak,
        "hard_violations": hard,
    }


def render(result):
    """A report a maintainer can read in the CI log without unfolding it."""
    lines = [
        f"QoR Pareto score: {result['verdict'].upper()}",
        f"  {result['reason']}",
    ]
    if "designs" in result:
        lines.append(
            f"  {len(result['designs'])} designs, "
            f"{result.get('witnesses_required', '?')} witnesses required"
        )
    for axis, ds in sorted(result.get("improved", {}).items()):
        lines.append(f"  + {axis:12s} {len(ds):2d} design(s): {', '.join(ds)}")
    for axis, ds in sorted(result.get("regressed", {}).items()):
        lines.append(f"  - {axis:12s} {len(ds):2d} design(s): {', '.join(ds)}")
    if result.get("unsupported_axes"):
        lines.append(
            "  ? unresolved: "
            + ", ".join(result["unsupported_axes"])
            + " (too few witnesses -- NOT the same as no effect)"
        )
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("verdicts", nargs="+", help="per-design check_pareto --json output")
    ap.add_argument("--witnesses", type=int, default=2)
    ap.add_argument(
        "--identical",
        default="",
        help="comma-separated designs whose results were bit-identical to "
        "baseline; when every design is listed the verdict is `inert`",
    )
    ap.add_argument("--out", default="", help="write the fleet verdict as JSON here")
    ap.add_argument(
        "--fail-on",
        default="worse",
        help="comma-separated verdicts that exit non-zero. Default is `worse` "
        "alone: a trade is a legitimate PR, and did-not-resolve is a "
        "statement about the instrument, not about the change.",
    )
    args = ap.parse_args(argv)

    result = score(
        load(args.verdicts),
        witnesses=args.witnesses,
        identical=[d for d in args.identical.split(",") if d],
    )
    print(render(result))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2)

    fail = set(v for v in args.fail_on.split(",") if v)
    return 1 if result["verdict"] in fail else 0


if __name__ == "__main__":
    sys.exit(main())
