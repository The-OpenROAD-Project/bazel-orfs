"""Does the estimator order distributions the way the flow does?

This is the measurement that licenses everything else. The CI gate never
runs the flow; it claims that an estimator ensemble reaches the same
verdict a flow ensemble would. That claim has to be checked once, on a
design where a flow ensemble is affordable, before it can be relied on
where one is not.

`multiplier` is that design: its flow is 47s, so 41 runs per variant cost
half an hour instead of ten.

## What is and is not being asked

NOT "does the estimator predict the flow's number". It does not, and it
does not need to: the estimator is biased, its per-perturbation response
is uncorrelated with the flow's (rho measured at -0.20..+0.14), and its
magnitudes run about 2x the flow's. All of that is allowed.

What is asked is whether the two agree on the ORDERING of the two
distributions -- the sign of the shift, and whether the effect clears
each arm's own noise. That is the weakest claim the gate needs, and the
only one with a chance of holding.

## The variants

base    reference
split   an algebraically identical rewrite of the multiply. Provably
        cannot change what the circuit computes, and costs the flow 9.6%
        of the achieved period. A large effect from a semantically
        neutral edit.
load8   one XOR level on eight low bits: a real but small change, near
        the resolution limit, which is where a gate either earns its
        keep or does not.

Agreement on `split` says the gate catches a large regression. Agreement
on `load8` -- or an honest "inconclusive" from both arms -- says it
behaves sensibly at the edge, which matters more.
"""

import argparse
import json
import os
import random
import statistics

from ci_gate import achieved, bootstrap, hodges_lehmann, prob_better
from optuna_study import run_estimator_pool

# The same rung the gate uses, stated explicitly, zeros included.
RUNG = {
    "RUN_PLACE": "1",
    "RUN_MACRO_PLACE": "0",
    "PLACE_IOS": "0",
    "GPL_TIMING_DRIVEN": "0",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_VIRTUAL_CTS": "0",
    "CLOCK_MODE": "none",
    "RUN_REPAIR_DESIGN": "0",
    "RUN_GRT": "0",
    "RUN_REPAIR_TIMING": "0",
}

EPS = list(range(-20, 21))

# multiplier_top places macros, so its rung must too -- the whole point of
# that design is that macro placement is in the loop and dominates the
# spread. Its reference ensemble is 15 perturbations rather than 41,
# because a 900s flow run caps how many can be afforded.
RUNG_MACRO = dict(RUNG, RUN_MACRO_PLACE="1")
EPS_TOP = list(range(-4, 5))


def verdict(base, change, rng):
    """The gate's own statistics, applied to whichever arm is passed."""
    if len(base) < 3 or len(change) < 3:
        return None
    shift = hodges_lehmann(base, change)
    p = prob_better(base, change)
    (slo, shi), (plo, phi) = bootstrap(base, change, rng, resamples=1500)
    mid = statistics.median(base)
    return {
        "n_base": len(base),
        "n_change": len(change),
        "shift_pct": 100.0 * shift / mid,
        "shift_ci_pct": [100.0 * slo / mid, 100.0 * shi / mid],
        "p": p,
        "p_ci": [plo, phi],
        "points": 100.0 * (2.0 * p - 1.0),
        "conclusive": not (plo <= 0.5 <= phi),
        "direction": "worse" if p < 0.5 else "better",
    }


def show(tag, v):
    if v is None:
        print(f"{tag:>22s}  (too few members)")
        return
    call = f"{v['direction'].upper()}" if v["conclusive"] else "inconclusive"
    print(
        f"{tag:>22s}  shift {v['shift_pct']:+7.2f}% "
        f"[{v['shift_ci_pct'][0]:+6.2f},{v['shift_ci_pct'][1]:+6.2f}]  "
        f"P={v['p']:.3f} [{v['p_ci'][0]:.3f},{v['p_ci'][1]:.3f}]  "
        f"{v['points']:+6.1f}pts  {call}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("truth_json", help="path list every arm measures")
    ap.add_argument("--flow", action="append", default=[], metavar="NAME:EPS:PATH")
    ap.add_argument("--estimator", action="append", default=[], metavar="NAME:EXE")
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument(
        "--macro-rung",
        action="store_true",
        help="place macros in the estimator arm, for a design that has them",
    )
    ap.add_argument(
        "--eps",
        choices=("wide", "top"),
        default="wide",
        help="perturbation set: 41 values, or the 15 the top reference uses",
    )
    args = ap.parse_args()

    rung = RUNG_MACRO if args.macro_rung else RUNG
    eps_set = EPS_TOP if args.eps == "top" else EPS

    rng = random.Random(0)
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()

    flow = {}
    for spec in args.flow:
        name, eps, path = spec.split(":", 2)
        flow.setdefault(name, {})[int(eps)] = achieved(path)

    est = {}
    for spec in args.estimator:
        name, exe = spec.split(":", 1)
        keep = os.path.join(ws, "tmp", f"validate_{name}")
        print(f"estimator ensemble: {name}")
        envs = {f"e{e}": dict(rung, CORE_AREA_EPS_SITES=str(e)) for e in eps_set}
        got = run_estimator_pool(
            exe, envs, args.truth_json, keep_results_dir=keep, jobs=args.jobs
        )
        for e in eps_set:
            if got.get(f"e{e}") is not None:
                est.setdefault(name, {})[e] = achieved(os.path.join(keep, f"e{e}.json"))

    report = {}
    print("\n" + "=" * 100)
    print("Does the estimator reach the flow's verdict?")
    print("=" * 100)
    for name in sorted(set(flow) | set(est)):
        if name == "base":
            continue
        fb, fc = flow.get("base"), flow.get(name)
        eb, ec = est.get("base"), est.get(name)
        fv = verdict(list(fb.values()), list(fc.values()), rng) if fb and fc else None
        ev = verdict(list(eb.values()), list(ec.values()), rng) if eb and ec else None
        print(f"\n{name}:")
        show("flow", fv)
        show("estimator", ev)
        agree = None
        if fv and ev:
            # The claim under test is about ordering, not magnitude: same
            # direction, and the same call on whether it clears the noise.
            agree = (
                fv["direction"] == ev["direction"]
                and fv["conclusive"] == ev["conclusive"]
            )
            print(
                f"{'agreement':>22s}  "
                + ("YES" if agree else "NO")
                + (
                    ""
                    if agree
                    else "  <- the estimator and the flow disagree on this variant"
                )
            )
        report[name] = {"flow": fv, "estimator": ev, "agree": agree}

    agreed = [n for n, r in report.items() if r["agree"]]
    total = [n for n, r in report.items() if r["agree"] is not None]
    print("\n" + "=" * 100)
    print(f"agreement on {len(agreed)}/{len(total)} variants: {', '.join(agreed)}")
    print(
        "Magnitudes are NOT expected to match -- the estimator is biased and"
        " uncorrelated\nwith the flow per perturbation. Only the ordering has"
        " to carry over."
    )

    out = os.path.join(
        ws,
        "test/estimation_ladder",
        "method_validation_top.json" if args.macro_rung else "method_validation.json",
    )
    with open(out, "w") as f:
        json.dump(
            {
                "variants": report,
                "flow": {k: {str(e): v for e, v in d.items()} for k, d in flow.items()},
                "estimator": {
                    k: {str(e): v for e, v in d.items()} for k, d in est.items()
                },
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
