"""Is a real RTL change detectable at all, against the flow's own spread?

The question a developer actually asks is "did my change help".  The
usual answer is to run the flow and compare the achieved period.  The
theory this tests is that the answer is worthless -- not because the flow
is slow, but because **one flow run is one draw from a distribution wider
than the effect being looked for**.  If that holds, an infinitely fast
flow would still not answer the question, and latency was never the
binding constraint.  Variance was.

## The design

Two things are needed and neither is available by inspection: a set of
RTL edits whose *true* effect is known, and an estimate of the spread.

multiplier_fuzz.sv supplies the first.  Three of its knobs are
equivalence-preserving -- statement order, identity wires, and an
algebraically identical split multiply -- so their true effect on the
achieved period is **exactly zero**, and any effect measured for them is
noise by construction.  This is Kahng & Reda's zero-change netlist
transformation (ISPD 2005) lifted to RTL.  EXTRA_ADD_STAGES is the
effect-size dial: N real logic levels, a genuine and monotone change.
Without the dial we could report a floor but not the smallest real change
anyone can detect against it.

The spread comes from running every variant at five site-aligned
core-area perturbations, through the real flow *and* through the
estimator.  Both arms see the **same** perturbation set, which makes the
comparison paired rather than unpaired -- common random numbers, the
standard variance-reduction trick.  It matters a lot:

    Var(estimated delta - true delta) = 2 * sigma^2 * (1 - rho)

so a consistently-wrong estimator is fine for answering "better or
worse", as long as it is wrong the *same way* on both arms.  Only rho
matters, and rho is what this measures.

## What is compared, and why not per-path

Across variants the netlist changes, so sampled paths cannot be matched
by name -- a re-synthesised design does not have the same instances.  The
comparison is therefore on **design-level** statistics: the achieved
period (the worst sampled path) and the distribution of the sampled
periods.  Pairing survives across perturbations, not across paths, so the
per-path power that a same-netlist comparison would have is not available
here.  That is a real limitation and not a presentational one.

## What a verdict means

For each variant, against the base:

    true effect      from the flow arm, as a distribution over eps
    measured effect  from the estimator arm, over the same eps
    detectable       is |effect| larger than what this many runs can
                     resolve?  gap >= z * s * sqrt(2/k)

An equivalence-preserving variant that comes out "detectable" is a false
positive, and it is the most interesting single number here: it is the
rate at which the flow reports an improvement that does not exist.
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import tempfile

from optuna_study import run_estimator_batch, scratch_root

# Two-sided ~95% factor, as in seed_sensitivity.verdict.
Z = 2.0

# What each variant's true effect on the achieved period is supposed to be.
# A label only: which variants actually run comes from the --flow and
# --estimator arguments, so adding one in BUILD.bazel cannot silently drop
# it from the analysis. An earlier version hardcoded the list here too and
# duly ignored four new variants.
TRUE_EFFECT = {
    "base": "reference",
    "order": "zero",
    "alias": "zero",
    "split": "zero",
    "load1": "real",
    "load8": "real",
    "load32": "real",
    "dial1": "real",
    "dial2": "real",
    "dial4": "real",
    "dial8": "real",
    # multiplier_top family
    "roworder": "zero",
    "tree": "zero",
    "stage1": "real",
    "stage2": "real",
    "stage4": "real",
}


def variant_order(*arms):
    """Variants actually present, base first, then by name.

    Derived from the data rather than from TRUE_EFFECT so the two cannot
    drift apart.
    """
    seen = set()
    for arm in arms:
        seen |= set(arm or {})
    rest = sorted(v for v in seen if v != "base")
    return (["base"] if "base" in seen else []) + rest


def effect_label(variant):
    return TRUE_EFFECT.get(variant, "?")


EPS_ORDER = ["m2", "m1", "0", "p1", "p2"]

# The estimator-side equivalent of the flow's CORE_AREA nudge, in whole
# sites. Same perturbation, same order, so the two arms are blocked
# identically and can be correlated pair by pair.
EPS_SITES = {"m2": -2, "m1": -1, "0": 0, "p1": 1, "p2": 2}

# The estimator configurations to compare, and the reason there is more
# than one.
#
# The per-stage study found timing-driven global placement to be the SOLE
# amplifier of constraint noise -- nudges at CTS, repair_design and global
# route moved the answer by exactly zero. That raises the question this
# table exists to answer: is timing-driven placement also the source of
# the SIGNAL, or only of the noise? If only noise, then turning it off
# makes the A/B verdict both cheaper and more precise, which would be the
# best available outcome. If the signal goes with it, noise and
# sensitivity share a mechanism and an ensemble is the only way out.
#
# So the rungs are chosen to isolate that knob (place_only vs place_td,
# and grt vs grt_td) rather than to trace the accuracy Pareto front, which
# is a different question already answered in README.md.
# Every gating knob, stated explicitly in every rung, including the zeros.
#
# This is not style. est_flag falls back to the environment when a knob is
# absent from the manifest, and GPL_TIMING_DRIVEN and
# GPL_ROUTABILITY_DRIVEN are real ORFS variables that the flow defaults to
# 1. So an omitted knob does not mean "off", it means "whatever ORFS
# decided" -- and the first version of this table omitted them, with the
# result that all four rungs silently ran the SAME timing-driven,
# routability-driven placement and produced identical numbers. The leaves
# now record gp_args so that failure is visible rather than merely
# suspicious.
RUNG_OFF = {
    "RUN_PLACE": "0",
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

# The alternatives to decide between. The per-stage study found
# timing-driven global placement to be the sole amplifier of constraint
# noise, so the question these isolate is whether it is also the source of
# the SIGNAL. If the A/B verdict survives with it off, the estimator gets
# cheaper and more precise at once; if the verdict goes with it, noise and
# sensitivity share a mechanism and only an ensemble helps.
# On a design with macros, macro placement runs in every rung. It is the
# biggest lever on top-level QoR and often the thing a change is trying to
# move, and nothing can tell us programmatically which changes affect it,
# so a gate that skipped it would be blind to the class of change that
# matters most. The cost lever is RTLMP effort, not its absence.
#
# Phase 1 measured why this matters: a 0.054um core nudge moves all 16
# macros by 143um on average and the achieved period by up to 15%.
RUNGS_MACRO = {
    "mp_place_only": dict(RUNG_OFF, RUN_PLACE="1", RUN_MACRO_PLACE="1"),
    "mp_place_td": dict(
        RUNG_OFF, RUN_PLACE="1", RUN_MACRO_PLACE="1", GPL_TIMING_DRIVEN="1"
    ),
    "mp_grt": dict(
        RUNG_OFF,
        RUN_PLACE="1",
        RUN_MACRO_PLACE="1",
        RUN_GRT="1",
        GRT_ITERATIONS="20",
    ),
}

RUNGS = {
    "place_only": dict(RUNG_OFF, RUN_PLACE="1"),
    "place_td": dict(RUNG_OFF, RUN_PLACE="1", GPL_TIMING_DRIVEN="1"),
    "place_rout": dict(RUNG_OFF, RUN_PLACE="1", GPL_ROUTABILITY_DRIVEN="1"),
    "grt": dict(RUNG_OFF, RUN_PLACE="1", RUN_GRT="1", GRT_ITERATIONS="20"),
    "grt_td_rd": dict(
        RUNG_OFF,
        RUN_PLACE="1",
        GPL_TIMING_DRIVEN="1",
        GPL_ROUTABILITY_DRIVEN="1",
        RUN_REPAIR_DESIGN="1",
        RUN_GRT="1",
        GRT_ITERATIONS="20",
    ),
}


def achieved_period(path_json):
    """The design's achieved period: the worst sampled path.

    Netlist-independent, which is what lets variants with different
    netlists be compared at all.
    """
    with open(path_json, "r") as f:
        return max(p["min_period"] for p in json.load(f)["paths"])


def timing_fingerprint(path_json):
    """A hash of the sorted sampled periods.

    Two variants that agree here did not merely land on the same achieved
    period -- synthesis produced timing-identical results, i.e. the RTL
    edit was absorbed entirely and never reached the netlist.  Worth
    reporting rather than inferring from a delta of 0.000, which is also
    what a bug that read the same file twice would print.
    """
    with open(path_json, "r") as f:
        periods = sorted(p["min_period"] for p in json.load(f)["paths"])
    blob = ",".join("%.6f" % v for v in periods).encode()
    return "%s:%d" % (hashlib.sha256(blob).hexdigest()[:12], len(periods))


def read_edge_memory(edges_jsonl):
    """Per-stage private-dirty memory, from the walk's own edge log.

    What an extra ensemble member costs is not a whole run's memory: fork
    children are copy-on-write, so shared pages are paid once and the
    marginal cost is the pages a child has dirtied. That is what bounds k
    alongside cores, and it has to be measured per stage because the
    stages differ wildly -- global placement rewrites every instance
    location, global route builds its own grid.
    """
    if not os.path.exists(edges_jsonl):
        return None
    by_stage = {}
    with open(edges_jsonl, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            kb = rec.get("private_dirty_kb")
            if kb is None or kb < 0:
                continue
            by_stage.setdefault(rec["stage"], []).append(kb / 1024.0)
    return {
        stage: {
            "max_private_dirty_mb": max(v),
            "median_private_dirty_mb": statistics.median(v),
            "n": len(v),
        }
        for stage, v in by_stage.items()
    }


def spread(values):
    if len(values) < 2:
        return {"mean": values[0] if values else float("nan"), "range": 0.0, "sd": 0.0}
    return {
        "mean": statistics.fmean(values),
        "range": max(values) - min(values),
        "sd": statistics.stdev(values),
    }


def paired_effect(variant_by_eps, base_by_eps):
    """Effect of a variant against the base, paired on the perturbation.

    d_e = P_variant(e) - P_base(e), one per perturbation, then the mean and
    the spread of those differences.  Pairing is the whole point: the
    common part of the noise -- whatever this particular core area does to
    both arms -- cancels, so the difference is far better determined than
    either number.
    """
    eps = [e for e in EPS_ORDER if e in variant_by_eps and e in base_by_eps]
    if not eps:
        return None
    diffs = [variant_by_eps[e] - base_by_eps[e] for e in eps]
    base_mean = statistics.fmean([base_by_eps[e] for e in eps])
    s = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    k = len(diffs)
    # What a k-run paired comparison can resolve. Using the spread of the
    # paired differences, which is already the (1-rho)-reduced quantity.
    mdd = Z * s * math.sqrt(2.0 / k) if s else 0.0
    mean_d = statistics.fmean(diffs)
    return {
        "k": k,
        "mean_delta": mean_d,
        "mean_delta_pct": 100.0 * mean_d / base_mean if base_mean else float("nan"),
        "sd_delta": s,
        "min_detectable": mdd,
        "min_detectable_pct": 100.0 * mdd / base_mean if base_mean else float("nan"),
        "detectable": abs(mean_d) > mdd,
        "per_eps": {e: variant_by_eps[e] - base_by_eps[e] for e in eps},
    }


def correlation(a_by_eps, b_by_eps):
    """rho between the two arms' deviations across the shared eps set.

    This is the number the whole scheme rests on. High rho means the
    estimator moves the way the flow moves, so a paired estimator
    comparison inherits the flow's answer at a fraction of the cost. rho
    near zero means the estimator's ensemble says nothing about the
    flow's, and no amount of averaging fixes that.
    """
    eps = [e for e in EPS_ORDER if e in a_by_eps and e in b_by_eps]
    if len(eps) < 3:
        return None
    a = [a_by_eps[e] for e in eps]
    b = [b_by_eps[e] for e in eps]
    if statistics.pstdev(a) == 0 or statistics.pstdev(b) == 0:
        return None
    return statistics.correlation(a, b)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--flow",
        action="append",
        default=[],
        metavar="VARIANT:EPS:PATH",
        help="a flow-arm ground truth for one (variant, perturbation)",
    )
    ap.add_argument(
        "--estimator",
        action="append",
        default=[],
        metavar="VARIANT:EXE:TRUTH",
        help="the estimator executable for a variant, and the path list it "
        "should measure (that variant's own unperturbed ground truth)",
    )
    ap.add_argument("--skip-estimator", action="store_true")
    ap.add_argument(
        "--macro-rungs",
        action="store_true",
        help="use the rung table for designs with macros, where every rung "
        "runs rtl_macro_placer",
    )
    ap.add_argument(
        "--only-variant",
        default=None,
        help="restrict the estimator arm to one variant (diagnostics)",
    )
    ap.add_argument(
        "--dump-leaves",
        action="store_true",
        help="print each leaf's phase timings, to confirm the rung knobs "
        "actually reached the stages rather than trusting that they did",
    )
    args = ap.parse_args()

    global RUNGS
    if args.macro_rungs:
        RUNGS = RUNGS_MACRO

    # Populated by the estimator loop below, so it has to exist first.
    report_memory = {}

    # ---- flow arm -------------------------------------------------
    flow = {}
    fingerprints = {}
    for spec in args.flow:
        variant, eps, path = spec.split(":", 2)
        flow.setdefault(variant, {})[eps] = achieved_period(path)
        fingerprints.setdefault(variant, {})[eps] = timing_fingerprint(path)

    print("=== did the edit reach the netlist at all?")
    print("(same fingerprint as base => synthesis absorbed the edit entirely)")
    base_fp = fingerprints.get("base", {})
    for variant, by_eps in fingerprints.items():
        same = [e for e in EPS_ORDER if base_fp.get(e) and by_eps.get(e) == base_fp[e]]
        print(
            f"{variant:>8s} fingerprint(eps=0)={by_eps.get('0', 'n/a')}"
            f"  matches base at {len(same)}/{len(EPS_ORDER)} perturbations"
        )
    report_absorbed = [
        v
        for v, by_eps in fingerprints.items()
        if v != "base" and all(by_eps.get(e) == base_fp.get(e) for e in EPS_ORDER)
    ]

    # ---- estimator arm --------------------------------------------
    est = {rung: {} for rung in RUNGS}
    runtimes = {rung: [] for rung in RUNGS}
    if not args.skip_estimator:
        for spec in args.estimator:
            variant, exe, truth = spec.split(":", 2)
            if args.only_variant and variant != args.only_variant:
                continue
            # Every rung and every perturbation in ONE manifest, so the
            # fork walk shares whatever they have in common: the design
            # load for all of them, and the floorplan/pin/macro prefix
            # within each perturbation. Splitting by rung or by
            # perturbation would re-pay that prefix each time and throw
            # away the only reason an ensemble is affordable.
            manifest = {
                f"{rung}__{eps}": dict(knobs, CORE_AREA_EPS_SITES=str(sites))
                for rung, knobs in RUNGS.items()
                for eps, sites in EPS_SITES.items()
            }
            scratch = tempfile.mkdtemp(prefix=f"fuzz_{variant}_", dir=scratch_root())
            leaves = os.path.join(scratch, "leaves")
            try:
                got = run_estimator_batch(
                    exe, manifest, truth, parallel=True, keep_results_dir=leaves
                )
                for rung in RUNGS:
                    for eps in EPS_SITES:
                        cid = f"{rung}__{eps}"
                        if got.get(cid) is None:
                            continue
                        est[rung].setdefault(variant, {})[eps] = achieved_period(
                            os.path.join(leaves, f"{cid}.json")
                        )
                        rt = got[cid].get("runtime_s")
                        if rt:
                            runtimes[rung].append(rt)
                if args.dump_leaves:
                    print(f"\n--- leaves for {variant}")
                    for rung in RUNGS:
                        for eps in EPS_SITES:
                            cid = f"{rung}__{eps}"
                            leaf = os.path.join(leaves, f"{cid}.json")
                            if not os.path.exists(leaf):
                                print(f"{cid:>22s}  MISSING")
                                continue
                            with open(leaf, "r") as fh:
                                d = json.load(fh)
                            ph = d.get("phases", {})
                            print(
                                f"{cid:>22s}  achieved={max(p['min_period'] for p in d['paths']):9.4f}"
                                f"  gp={ph.get('global_place', 0):6.2f}"
                                f"  rd={ph.get('repair_design', 0):6.2f}"
                                f"  grt={ph.get('global_route', 0):6.2f}"
                                f"  gp_args={d.get('gp_args', '?')}"
                            )
                mem = read_edge_memory(os.path.join(leaves, "edges.jsonl"))
                if mem:
                    report_memory.setdefault(variant, mem)
            finally:
                shutil.rmtree(scratch, ignore_errors=True)

    # ---- report ---------------------------------------------------
    report = {
        "z": Z,
        "true_effect": TRUE_EFFECT,
        "fingerprints": fingerprints,
        "absorbed_by_synthesis": report_absorbed,
        "rungs": RUNGS,
    }
    arms = ([("flow", flow)] if flow else []) + [
        ("est:%s" % rung, est[rung]) for rung in RUNGS if est.get(rung)
    ]
    for arm_name, arm in arms:
        if not arm:
            continue
        print(f"\n=== {arm_name} arm: achieved period per variant")
        print(
            f"{'variant':>8s} {'true':>9s} {'mean':>10s} {'range':>8s} "
            f"{'range%':>7s} {'delta':>9s} {'delta%':>8s} {'MDD%':>7s} {'called':>9s}"
        )
        base = arm.get("base")
        for variant in variant_order(arm):
            by_eps = arm.get(variant)
            if not by_eps:
                continue
            sp = spread([by_eps[e] for e in EPS_ORDER if e in by_eps])
            row = {"spread": sp, "per_eps": by_eps}
            eff = paired_effect(by_eps, base) if base and variant != "base" else None
            row["effect"] = eff
            report.setdefault(arm_name, {})[variant] = row
            rng_pct = 100.0 * sp["range"] / sp["mean"] if sp["mean"] else float("nan")
            if eff:
                called = "CHANGED" if eff["detectable"] else "no change"
                print(
                    f"{variant:>8s} {effect_label(variant):>9s} {sp['mean']:>10.3f} "
                    f"{sp['range']:>8.3f} {rng_pct:>6.3f}% {eff['mean_delta']:>9.3f} "
                    f"{eff['mean_delta_pct']:>7.3f}% {eff['min_detectable_pct']:>6.3f}% "
                    f"{called:>9s}"
                )
            else:
                print(
                    f"{variant:>8s} {effect_label(variant):>9s} {sp['mean']:>10.3f} "
                    f"{sp['range']:>8.3f} {rng_pct:>6.3f}%"
                )

    # ---- the number the scheme rests on ---------------------------
    # ---- the decision table -------------------------------------
    # For each estimator rung: does its verdict match the flow's, and what
    # did that cost? This is the table the CI configuration is chosen from.
    if flow and any(est.values()):
        print("\n=== verdict agreement per rung (the flow is the reference)")
        print(
            f"{'rung':>11s} {'agree':>7s} {'false+':>7s} {'missed':>7s} "
            f"{'signflip':>9s} {'MDD%':>7s} {'median s':>9s}"
        )
        for rung in RUNGS:
            arm = est.get(rung)
            if not arm or "base" not in arm:
                continue
            agree = fp = missed = signflip = 0
            mdds = []
            for variant in variant_order(arm, flow):
                if variant == "base":
                    continue
                fe = report.get("flow", {}).get(variant, {}).get("effect")
                ee = report.get("est:%s" % rung, {}).get(variant, {}).get("effect")
                if not fe or not ee:
                    continue
                mdds.append(ee["min_detectable_pct"])
                if fe["detectable"] == ee["detectable"]:
                    agree += 1
                elif ee["detectable"]:
                    fp += 1
                else:
                    missed += 1
                # A sign flip is the failure that actually costs a day: the
                # estimator says a change helped when the flow says it hurt.
                if (
                    fe["detectable"]
                    and ee["detectable"]
                    and fe["mean_delta"] * ee["mean_delta"] < 0
                ):
                    signflip += 1
            med = statistics.median(runtimes[rung]) if runtimes[rung] else float("nan")
            print(
                f"{rung:>11s} {agree:>7d} {fp:>7d} {missed:>7d} {signflip:>9d} "
                f"{statistics.fmean(mdds) if mdds else float('nan'):>6.2f}% {med:>9.1f}"
            )
            report.setdefault("agreement", {})[rung] = {
                "agree": agree,
                "false_positive": fp,
                "missed": missed,
                "sign_flip": signflip,
                "mean_mdd_pct": statistics.fmean(mdds) if mdds else None,
                "median_runtime_s": med,
            }

        print("\n=== does the estimator track the flow? (rho across perturbations)")
        for rung in RUNGS:
            if not est.get(rung):
                continue
            rhos = [
                correlation(flow[v], est[rung][v])
                for v in variant_order(flow, est[rung])
                if v in flow and v in est[rung]
            ]
            rhos = [r for r in rhos if r is not None]
            shown = "n/a" if not rhos else "%+.3f" % statistics.fmean(rhos)
            print(f"{rung:>11s} mean rho over variants = {shown}")
            report.setdefault("rho", {})[rung] = rhos

    # ---- power curve: detection vs true effect size ---------------
    if flow and any(est.values()):
        print("\n=== power curve: true effect (flow) vs what each rung called")
        hdr = f"{'variant':>8s} {'true%':>8s}"
        for rung in RUNGS:
            hdr += f" {rung:>11s}"
        print(hdr)
        rows = []
        for variant in variant_order(flow):
            if variant == "base":
                continue
            fe = report.get("flow", {}).get(variant, {}).get("effect")
            if not fe:
                continue
            rows.append((abs(fe["mean_delta_pct"]), variant, fe))
        for _, variant, fe in sorted(rows):
            line = f"{variant:>8s} {fe['mean_delta_pct']:>7.2f}%"
            for rung in RUNGS:
                ee = report.get("est:%s" % rung, {}).get(variant, {}).get("effect")
                if not ee:
                    line += f" {'-':>11s}"
                else:
                    mark = "CHANGED" if ee["detectable"] else "quiet"
                    line += f" {mark:>11s}"
            print(line)

    # ---- the headline --------------------------------------------
    if flow:
        zeros = [
            v
            for v in variant_order(flow)
            if effect_label(v) == "zero"
            and report.get("flow", {}).get(v, {}).get("effect")
        ]
        false_pos = [v for v in zeros if report["flow"][v]["effect"]["detectable"]]
        print(
            f"\nEquivalence-preserving variants whose TRUE effect is zero: "
            f"{len(zeros)}.  The flow called {len(false_pos)} of them a real "
            f"change{': ' + ', '.join(false_pos) if false_pos else ''}."
        )
        report["false_positives"] = false_pos

    if report_memory:
        print("\n=== marginal memory per forked ensemble member (private dirty)")
        stages = sorted({st for m in report_memory.values() for st in m})
        for stage in stages:
            vals = [
                m[stage]["max_private_dirty_mb"]
                for m in report_memory.values()
                if stage in m
            ]
            print(f"{stage:>14s} max {max(vals):>8.1f} MB")
        report["memory"] = report_memory

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    out = os.path.join(ws, "test/estimation_ladder", "fuzz_floor.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
