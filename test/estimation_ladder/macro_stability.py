"""Is `rtl_macro_placer` deterministic, thread-independent, and stable?

Phase 1 of the `multiplier_top` CI-gate campaign, and it runs first
because any of its three answers can change the rest of the plan before a
single 900s flow run is paid for.

## Why these three questions

**Determinism.** The RTL-MP papers describe a "go-with-the-winners" /
multi-start scheme with the thread count set to 10. If which start wins
depends on scheduling, the macro placer is nondeterministic run to run,
and every downstream measurement in this study needs a larger ensemble
than planned. The rest of the study has so far relied on OpenROAD being
deterministic for identical inputs; that is checked here for the one
stage where the literature gives a specific reason to doubt it.

**Thread independence.** Threads do not survive `fork()` and the worker
pools are respawned inside each child (docs/fork.md). If the macro
placement depends on the thread count, then an ensemble whose members get
different thread counts -- which is exactly what
`run_estimator_batch` does today, dividing cores by the manifest size --
is injecting the scheduler into the measurement as an uncontrolled
perturbation. Then `NUM_CORES` must be pinned and recorded everywhere.

**Chaos.** How far do the macros actually move when the core rectangle is
nudged by one site? This is measured directly, in microns, rather than
through its effect on the period: the timing consequence depends on the
estimator's model being right, and macro displacement does not. It is
also what sizes the `k` a gate will need.

## Why macro placement is not simply held fixed

It would be much cheaper to pin the macro placement and share it. That is
rejected on purpose: macro placement is the biggest lever on top-level
QoR and frequently the thing a change is trying to move, and nothing can
tell us programmatically whether a given edit affects it. A gate that
pinned it would be blind to the class of change that matters most. So it
runs everywhere, and its contribution is measured instead of removed.

## The configuration

Global placement is switched OFF. Only floorplan, pin placement and macro
placement run, so the recorded origins are `rtl_macro_placer`'s output and
nothing else's -- and a point costs about 25s instead of 66s.
"""

import argparse
import json
import os
import shutil
import statistics
import tempfile

from optuna_study import run_estimator, run_estimator_batch, scratch_root

# Everything off except what is needed to place macros. Stated
# explicitly, zeros included: an omitted knob means "whatever ORFS
# defaults to", and GPL_TIMING_DRIVEN and GPL_ROUTABILITY_DRIVEN are real
# ORFS variables defaulted to 1. Omitting them silently made four rungs
# identical in the previous campaign.
RUNG = {
    "RUN_PLACE": "0",
    "RUN_MACRO_PLACE": "1",
    "PLACE_IOS": "0",
    "GPL_TIMING_DRIVEN": "0",
    "GPL_ROUTABILITY_DRIVEN": "0",
    "GPL_VIRTUAL_CTS": "0",
    "CLOCK_MODE": "none",
    "RUN_REPAIR_DESIGN": "0",
    "RUN_GRT": "0",
    "RUN_REPAIR_TIMING": "0",
}

SPINE = "spine"

# A second rung that actually places cells, so the timing consequence of a
# macro reshuffle can be put next to the reshuffle itself. Displacement
# alone does not say whether QoR moved: the placer may have found an
# equally good arrangement somewhere else on the die, and that distinction
# is the whole question for a gate.
PLACED_RUNG = dict(RUNG, RUN_PLACE="1")

# One site is 0.054um on asap7 (from //test/estimation_ladder:site_probe).
EPS_SITES = [-2, -1, 1, 2]

# Thread counts to compare. Pinned per run, never divided across an
# ensemble, which is the whole point of the check.
THREAD_COUNTS = [1, 4, 16]


def macros(leaf_json):
    """Macro origins, in database units, keyed by instance name."""
    with open(leaf_json, "r") as f:
        data = json.load(f)
    return data.get("macros", {}), data.get("dbu_per_micron", 1000)


def displacement(a_json, b_json):
    """How far the macros moved between two runs, in microns.

    Manhattan distance per instance. Returns None if the two runs do not
    even agree on which macros exist, which would mean the comparison is
    meaningless rather than large.
    """
    a, dbu = macros(a_json)
    b, _ = macros(b_json)
    if not a or set(a) != set(b):
        return None
    d = [
        (abs(a[k][0] - b[k][0]) + abs(a[k][1] - b[k][1])) / float(dbu)
        for k in sorted(a)
    ]
    orient_changed = sum(1 for k in a if a[k][2] != b[k][2])
    return {
        "n_macros": len(d),
        "moved": sum(1 for v in d if v > 0.0),
        "mean_um": statistics.fmean(d),
        "max_um": max(d),
        "orientation_changed": orient_changed,
    }


def show(tag, disp):
    if disp is None:
        print(f"{tag:>28s}  (macro sets differ -- not comparable)")
        return
    print(
        f"{tag:>28s}  moved {disp['moved']:>3d}/{disp['n_macros']:<3d}"
        f"  mean {disp['mean_um']:>9.3f}um  max {disp['max_um']:>9.3f}um"
        f"  orient {disp['orientation_changed']}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("estimator_exe")
    ap.add_argument("ground_truth_json")
    ap.add_argument("design_name")
    args = ap.parse_args()

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    out_dir = os.path.join(ws, "test/estimation_ladder")
    report = {"design": args.design_name, "rung": RUNG}

    scratch = tempfile.mkdtemp(prefix="macro_stability_", dir=scratch_root())
    leaves = os.path.join(scratch, "leaves")
    try:
        # --- determinism under fork, and chaos, in one walk ------------
        # The repeat carries an explicit zero so it differs from the spine
        # as a grouping key and the walk genuinely re-runs the stages,
        # rather than writing a second leaf from one execution.
        manifest = {SPINE: dict(RUNG)}
        manifest["repeat"] = dict(RUNG, CLK_PERIOD_EPS_FLOORPLAN="0")
        for eps in EPS_SITES:
            manifest[f"eps{eps}"] = dict(RUNG, CORE_AREA_EPS_SITES=str(eps))

        got = run_estimator_batch(
            args.estimator_exe,
            manifest,
            args.ground_truth_json,
            parallel=True,
            keep_results_dir=leaves,
        )
        missing = [cid for cid, m in got.items() if m is None]
        if missing:
            raise SystemExit(f"branches produced no leaf: {missing}")

        spine_leaf = os.path.join(leaves, f"{SPINE}.json")
        n_macros = len(macros(spine_leaf)[0])
        if n_macros == 0:
            raise SystemExit(
                "no macros recorded -- this probe is only meaningful on a "
                "design with macros, and est_macro_origins found none"
            )
        print(f"=== {args.design_name}: {n_macros} macros\n")

        print("--- determinism: a forked re-run of the identical config")
        rep = displacement(os.path.join(leaves, "repeat.json"), spine_leaf)
        show("repeat vs spine", rep)
        report["determinism"] = rep

        print("\n--- chaos: the core rectangle nudged by whole sites")
        report["chaos"] = {}
        for eps in EPS_SITES:
            d = displacement(os.path.join(leaves, f"eps{eps}.json"), spine_leaf)
            show(f"{eps:+d} site(s) vs spine", d)
            report["chaos"][str(eps)] = d
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    # --- does the reshuffle cost anything? -----------------------------
    print("\n--- timing consequence: the same nudges, with cells placed")
    placed_dir = tempfile.mkdtemp(prefix="macro_placed_")
    placed_leaves = os.path.join(placed_dir, "leaves")
    try:
        manifest = {SPINE: dict(PLACED_RUNG)}
        for eps in EPS_SITES:
            manifest[f"eps{eps}"] = dict(PLACED_RUNG, CORE_AREA_EPS_SITES=str(eps))
        got = run_estimator_batch(
            args.estimator_exe,
            manifest,
            args.ground_truth_json,
            parallel=True,
            keep_results_dir=placed_leaves,
        )
        periods = {}
        for cid in manifest:
            leaf = os.path.join(placed_leaves, f"{cid}.json")
            if got.get(cid) is None or not os.path.exists(leaf):
                continue
            with open(leaf, "r") as fh:
                periods[cid] = max(p["min_period"] for p in json.load(fh)["paths"])
        if len(periods) > 1:
            base = periods[SPINE]
            vals = list(periods.values())
            rng = max(vals) - min(vals)
            print(
                f"{'achieved period':>28s}  spine {base:.3f}"
                f"  range {rng:.3f} ({100.0 * rng / base:.2f}%)"
            )
            for cid in sorted(periods):
                if cid == SPINE:
                    continue
                d = periods[cid] - base
                disp = report["chaos"].get(cid.replace("eps", ""))
                moved = f"{disp['mean_um']:.1f}um" if disp else "n/a"
                print(
                    f"{cid:>28s}  period {periods[cid]:.3f}"
                    f"  delta {d:+.3f} ({100.0 * d / base:+.2f}%)"
                    f"  macros moved mean {moved}"
                )
            report["placed"] = {
                "periods": periods,
                "range_pct": 100.0 * rng / base,
            }
    finally:
        shutil.rmtree(placed_dir, ignore_errors=True)

    # --- thread independence ------------------------------------------
    # Separate processes, not forked children: the thread count is
    # process-wide and a child inherits whatever its parent had, so this
    # cannot be expressed as a dimension of the walk.
    print("\n--- thread independence: identical input, different NUM_CORES")
    thread_dir = tempfile.mkdtemp(prefix="macro_threads_", dir=scratch_root())
    try:
        refs = {}
        for threads in THREAD_COUNTS:
            out_json = os.path.join(thread_dir, f"t{threads}.json")
            run_estimator(
                args.estimator_exe,
                dict(RUNG, NUM_CORES=str(threads)),
                args.ground_truth_json,
                out_json=out_json,
            )
            refs[threads] = out_json
        base = refs[THREAD_COUNTS[0]]
        report["threads"] = {}
        for threads in THREAD_COUNTS[1:]:
            d = displacement(refs[threads], base)
            show(f"NUM_CORES={threads} vs {THREAD_COUNTS[0]}", d)
            report["threads"][str(threads)] = d
    finally:
        shutil.rmtree(thread_dir, ignore_errors=True)

    # --- the verdict ---------------------------------------------------
    det = report.get("determinism")
    thr = report.get("threads") or {}
    print("\n=== verdict")
    if det and det["moved"] == 0:
        print("  deterministic under fork: a re-run reproduced every macro exactly")
    else:
        print(
            "  NOT deterministic under fork -- every ensemble size in this\n"
            "  campaign is affected, and the null-control discipline has to\n"
            "  extend to macro placement"
        )
    moved_by_threads = [t for t, d in thr.items() if d and d["moved"] > 0]
    if moved_by_threads:
        print(
            f"  thread-DEPENDENT at NUM_CORES={', '.join(moved_by_threads)}:\n"
            "  NUM_CORES must be pinned and recorded for every run, and\n"
            "  run_estimator_batch's cores//len(manifest) split is injecting\n"
            "  the scheduler into the measurement"
        )
    else:
        print("  thread-independent: the placement did not move with NUM_CORES")

    path = os.path.join(out_dir, f"macro_stability_{args.design_name}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
