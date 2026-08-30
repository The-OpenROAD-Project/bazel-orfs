"""How stable is any of this?  Per-stage reproducibility of the front.

The Pareto fronts this study publishes are ranked by mean_rel_err, and
adjacent rungs sit 0.002 to 0.005 apart.  Every one of those numbers, and
every Kendall tau and every three-significant-figure calibration scale
factor, comes from a single run.  knob_sweep.py states the assumption
that makes that acceptable -- "accuracy is deterministic for a given
configuration, so repeating it would measure nothing" -- and it is true:
re-running the identical configuration gives the identical answer,
because OpenROAD is deterministic for identical inputs.

Determinism is not stability.  The question this asks is what happens
when an input moves by an amount nobody would call a design change.  If
the answer moves further than the gaps the front is ranked by, then the
ordering below the top rung is noise and the front is quoted to a
precision it does not have.

## This is somebody else's experiment

The method is not ours.  Kahng & Mantik (ISQED 2002) gave the taxonomy of
perturbations that leave a solution well-formed -- randomness, ordering
and naming, library richness, constraints, geometric properties -- and
measured tool noise with it.  Jeong & Kahng found a 1ps change in a
timing constraint moving post-synthesis area by up to 16.4%.  Chan, Kahng
& Woo (SLIP 2020) re-ran both on modern commercial tools, found 7% on
routed wirelength from netlist reordering and 11.5% from nudging a
placement blockage, and framed the result as a *noise floor*: a lower
bound on how accurate any predictor of that flow can be.  That framing is
why this file exists -- the estimation ladder is exactly such a
predictor, with published numbers, and nobody has checked them against
the floor.

Three things here are not in that literature.  The subject is OpenROAD
rather than a commercial tool.  The subject is a predictor being audited
rather than a flow being characterised.  And the noise is attributed
**per stage** rather than to the flow as a whole, which is affordable
only because of the next section.

## What this does NOT measure, and why the word matters

Write the estimate and the truth as functions of the perturbation:
E(eps) and T(eps).  Then

    Var(E - T) = sigma_E^2 + sigma_T^2      (if the two are independent)

and the *noise floor* in Chan/Kahng/Woo's sense is sigma_T: eps is not an
input the estimator is given, so for any predictor f that does not see
eps, E[(T(eps) - f)^2] >= sigma_T^2, with equality at f = mean(T).  No
estimator can beat the dispersion of its own target.

This study measures **sigma_E** -- the flow is not re-run at perturbed
inputs -- so it must not be called a noise floor.  sigma_E does not bound
achievable accuracy; it bounds something narrower and still worth having:
whether the published front is *reproducible*, i.e. whether ranking two
rungs by one run each is a measurement or a coin flip.  Measuring
sigma_T needs the flow-side arm, which is deliberately out of scope.

There is also no probability measure over eps -- nobody draws a random
seed, a designer runs one configuration -- so what is reported is a range
over a chosen neighbourhood,

    S = max |M(eps) - M(0)|  over the eps tried

a local stability radius rather than a standard deviation.  That is why
the papers quote max-minus-min (7%, 11.5%, 16.4%) and why this does too.
Using S where a sigma belongs, as verdict() does below, is conservative
and is labelled as such.

## Why it is cheap

Perturbing at stage S only requires the stages from S onward.  So the
walk is one unperturbed spine with a branch hanging off each stage:

    load - floorplan - pins_pre - macro_place - global_place - clock - grt
              |            |          |             |           |      |
           +-1 site    +-1 track   +0.001        +-1ps       +-1ps  +-1ps

The batch walk in estimator_batch.tcl groups configurations stage by
stage on the knobs that stage consumes and forks only where they differ,
so a configuration that differs from the spine only in CLK_PERIOD_EPS_GRT
shares the entire prefix and re-runs only global route.  Cost is one full
run plus the sum of the tails, not one full run per data point.  That is
what makes a per-stage answer possible at all, and it is why every
perturbation knob is keyed to a single stage.

So the whole manifest goes to run_estimator_batch in ONE call.  Splitting
it per stage would pay for the spine once per stage and throw the saving
away.

## The null controls, and the resolution floor they revealed

floorplan and pins_pre read no timing, so a clock-period nudge applied
there must leave the answer alone.  That is a free check on the whole
harness, and it is load-bearing: a perturbation that silently did nothing
would pass it and then report a spread of exactly zero everywhere, which
is the one wrong answer that looks like a clean result.
est_perturb_clock reads the period back and errors if the nudge did not
land, so the two guards cover each other.

"Alone" is not "bit-identical", and finding out why set the study's
resolution limit.  min_period = clk_period - slack cancels the nudge
exactly in real arithmetic, but OpenSTA keeps both terms in a 32-bit
float, so the cancellation leaves a residue of order float32 epsilon
times the period -- about 6e-5 on a 1000ps clock.  Measured: a 1ps nudge
at floorplan moves all 54 sampled paths by ~6e-5 (8.8e-8 relative),
while a 10ps nudge moves only 5 of them, because 1010 is exactly
representable in float32 and 1001 is not.  That is arithmetic, not tool
noise.

So the controls are checked to RELTOL below, and the study cannot resolve
anything finer than ~1e-7 relative.  That is three orders of magnitude
below the front gaps it is judging (5e-4 on mean_rel_err), so it is a
limit worth stating and not one that bites.

Thread count is deliberately absent.  Threads do not survive fork() and a
child inherits the process-wide count (docs/fork.md), so it cannot be a
dimension of this tree; measuring it needs separate processes and is a
different study.
"""

import argparse
import json
import math
import os
import shutil
import statistics
import tempfile

from estimation_metrics import time_unit
from optuna_study import run_estimator_batch, scratch_root

# The gaps the noise is judged against, written down BEFORE the study
# runs.  This is the whole reason the result is interpretable either way:
# a floor below these values certifies the front to a stated precision,
# and a floor above them condemns it.  A threshold picked after seeing
# the spread would certify nothing at all.
#
# Taken from the published fronts in README.md: the smallest mean_rel_err
# difference between adjacent front rungs on each design.
FRONT_GAP = {
    "multiplier": 0.0005,
    "multiplier_top": 0.0064,
    "multiplier_top_macro": 0.1253,
}

# Three rungs per design, from the published fronts: the cheapest, one in
# the middle and the most accurate.  The spread is a property of the
# configuration, not of the estimator in general -- a rung that runs no
# timing-driven stage has nothing for a constraint nudge to perturb -- so
# reporting one number for "the estimator" would be meaningless.
RUNGS = {
    "cheap": {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "0",
        "PLACE_IOS": "1",
    },
    "middle": {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "0",
        "GPL_TIMING_DRIVEN": "1",
        "RUN_REPAIR_DESIGN": "1",
        "RUN_GRT": "1",
        "GRT_ITERATIONS": "20",
    },
    "accurate": {
        "RUN_PLACE": "1",
        "RUN_MACRO_PLACE": "1",
        "GPL_TIMING_DRIVEN": "1",
        "GPL_ROUTABILITY_DRIVEN": "1",
        "CLOCK_MODE": "real",
        "RUN_REPAIR_DESIGN": "1",
        "RUN_GRT": "1",
        "GRT_ITERATIONS": "9",
        "RUN_REPAIR_TIMING": "1",
        "REPAIR_TIMING_ARGS": "-sequence {vt_swap reroute}",
    },
}

# Which perturbation each stage gets, and at what magnitudes.
#
# One knob per stage rather than one global knob, so the walk diverges
# where the perturbation takes effect (see the module docstring).  The
# clock-period nudge goes to every stage that reads timing because it is
# the only perturbation that cannot move the metric except through tool
# noise: min_period = clk_period - slack, so a period loosened by eps
# gives a slack larger by eps and the two cancel exactly.
#
# "gate" names the rung knob a stage needs before a perturbation there
# means anything: nudging the clock at a CTS that never runs measures
# nothing, and a stage that is off would report a spurious zero.
PERTURBATIONS = {
    "floorplan_area": {
        "stage": "floorplan",
        "knob": "CORE_AREA_EPS_SITES",
        "values": [-2, -1, 1, 2],
        "gate": None,
        "kind": "geometric",
    },
    "floorplan_rows": {
        "stage": "floorplan",
        "knob": "CORE_AREA_EPS_ROWS",
        "values": [-1, 1],
        "gate": None,
        "kind": "geometric",
    },
    # These two are constraint perturbations that is_null_control()
    # PROMOTES to null controls on a rung where nothing from that stage
    # onward reads timing.  The kind cannot be hardcoded here: a clock
    # nudge persists to the end of the run, so whether it is a control
    # depends on the rung, not on the stage that applies it.
    "floorplan_clock": {
        "stage": "floorplan",
        "knob": "CLK_PERIOD_EPS_FLOORPLAN",
        "values": [1, 10],
        "gate": None,
        "kind": "constraint",
    },
    "pins_clock": {
        "stage": "pins_pre",
        "knob": "CLK_PERIOD_EPS_PINS_PRE",
        "values": [1, 10],
        "gate": None,
        "kind": "constraint",
    },
    "macro_density": {
        "stage": "macro_place",
        "knob": "PLACE_DENSITY_EPS",
        "values": [0.001, -0.001],
        "gate": "RUN_PLACE",
        "kind": "geometric",
    },
    "macro_clock": {
        "stage": "macro_place",
        "knob": "CLK_PERIOD_EPS_MACRO_PLACE",
        "values": [1, 2, 5, 10],
        "gate": "RUN_MACRO_PLACE",
        "kind": "constraint",
    },
    "place_clock": {
        "stage": "global_place",
        "knob": "CLK_PERIOD_EPS_GLOBAL_PLACE",
        "values": [1, 2, 5, 10],
        "gate": "GPL_TIMING_DRIVEN",
        "kind": "constraint",
    },
    "cts_clock": {
        "stage": "clock",
        "knob": "CLK_PERIOD_EPS_CLOCK",
        "values": [1, 2, 5, 10],
        "gate": "CLOCK_MODE",
        "kind": "constraint",
    },
    "repair_clock": {
        "stage": "repair_design",
        "knob": "CLK_PERIOD_EPS_REPAIR_DESIGN",
        "values": [1, 2, 5, 10],
        "gate": "RUN_REPAIR_DESIGN",
        "kind": "constraint",
    },
    "grt_clock": {
        "stage": "grt",
        "knob": "CLK_PERIOD_EPS_GRT",
        "values": [1, 2, 5, 10],
        "gate": "RUN_GRT",
        "kind": "constraint",
    },
}

# Relative agreement required of a null control, set by float32 epsilon
# in OpenSTA's period storage rather than by taste -- see the module
# docstring.  Two orders above the ~1e-7 residue actually observed, and
# three orders below a nudge that failed to apply, which would move
# min_period by the whole of eps.
RELTOL = 1e-6

# Two-sided ~95% factor for the resolvability arithmetic in verdict().
Z = 2.0

# Configurations each design's sweep explored, from README.md. Used only
# for the selection-bias estimate, where what matters is the order of
# magnitude of ln(N).
N_EXPLORED = {
    "multiplier": 238,
    "multiplier_top": 231,
    "multiplier_top_macro": 234,
}

SPINE = "spine"

# The stages in flow order, and which rung knob makes each one read the
# clock constraint.  macro_place is absent on purpose: it consumes only
# the density target, not timing.
STAGE_ORDER = [
    "floorplan",
    "wire_rc",
    "pins_pre",
    "macro_place",
    "global_place",
    "clock",
    "repair_design",
    "grt",
    "repair_timing",
]

TIMING_DRIVEN = {
    "global_place": ("GPL_TIMING_DRIVEN", ("1",)),
    "clock": ("CLOCK_MODE", ("real",)),
    "repair_design": ("RUN_REPAIR_DESIGN", ("1",)),
    "grt": ("RUN_GRT", ("1",)),
    "repair_timing": ("RUN_REPAIR_TIMING", ("1",)),
}


def is_null_control(spec, rung):
    """Is this perturbation guaranteed to be a no-op for this rung?

    A clock nudge persists from the stage that applies it to the end of
    the run -- deliberately, so that "apply at S" perturbs S onwards and
    the difference between consecutive stages isolates one stage's
    contribution.  The consequence is that a nudge is only a null control
    when NO stage at or after it reads timing.

    Getting this wrong is what the first run of this study did: it
    labelled a floorplan nudge a control on a rung whose global placement
    was timing-driven, and duly reported the control as broken when it was
    the label that was broken.  The stage reads no timing; the run does.
    """
    if not spec["knob"].startswith("CLK_PERIOD_EPS"):
        return False
    start = STAGE_ORDER.index(spec["stage"])
    for stage in STAGE_ORDER[start:]:
        knob, on = TIMING_DRIVEN.get(stage, (None, ()))
        if knob and rung.get(knob, "0") in on:
            return False
    return True


def kind_of(spec, rung):
    if is_null_control(spec, rung):
        return "null_control"
    return spec["kind"]


def applicable(perturbation, rung):
    """Is this perturbation meaningful for this rung?

    A stage the rung never runs cannot be perturbed, and pretending
    otherwise would put a zero in the table that reads as "this stage is
    quiet" when it means "this stage was absent".
    """
    gate = perturbation["gate"]
    if gate is None:
        return True
    value = rung.get(gate, "0")
    return value not in ("0", "", "none")


def build_manifest(rung, repeats):
    """The spine plus one leaf per (perturbation, epsilon).

    Repeats of the spine are separate ids carrying an inert knob so the
    walk treats them as distinct configurations; they check that an
    identical configuration really does reproduce, which is the
    assumption the rest of the study rests on.
    """
    manifest = {SPINE: dict(rung)}
    for name, spec in PERTURBATIONS.items():
        if not applicable(spec, rung):
            continue
        for value in spec["values"]:
            manifest[f"{name}@{value}"] = dict(rung, **{spec["knob"]: str(value)})
    for i in range(1, repeats):
        # A repeat has to differ in some stage knob or the walk groups it
        # with the spine and writes its leaf from the SAME execution --
        # verifying the JSON writer rather than anything about
        # reproducibility.  An explicit zero does it: est_stage_key
        # distinguishes "knob unset" from an explicit value, so this forks
        # at the first stage and re-runs the whole spine, while
        # est_perturb_clock returns early on 0 and changes nothing.
        #
        # What this checks is fork reproducibility, not OpenROAD's:
        # threads do not survive fork() and the pools are respawned in the
        # child, so "a forked child computes what an inline run computes"
        # is an assumption of this harness worth testing rather than
        # assuming.  It costs one extra spine per repeat.
        manifest[f"{SPINE}_repeat{i}"] = dict(rung, CLK_PERIOD_EPS_FLOORPLAN="0")
    return manifest


def dispersion(values):
    """Max-minus-min as a fraction of the middle, and the stdev.

    Reported as a range rather than a variance because the papers this
    reproduces report ranges (7%, 11.5%, 16.4%) and the numbers should be
    comparable to theirs.
    """
    if len(values) < 2:
        return {"range_pct": 0.0, "stdev": 0.0, "n": len(values)}
    mid = statistics.fmean(values)
    span = max(values) - min(values)
    return {
        "range_pct": 100.0 * span / mid if mid else float("nan"),
        "stdev": statistics.pstdev(values),
        "n": len(values),
    }


def critical_period(leaf_json):
    """A run's predicted achieved period: its worst sampled path."""
    return max(path_periods(leaf_json).values())


def path_periods(leaf_json):
    with open(leaf_json, "r") as f:
        return {(p["start"], p["end"]): p["min_period"] for p in json.load(f)["paths"]}


def paths_agree(a_json, b_json, reltol=RELTOL):
    """Do two runs agree on every sampled path, to float32 precision?

    Every path, not merely the worst one: a control that compared only
    critical periods would pass while the perturbation quietly reshuffled
    everything beneath it, which is exactly the failure it exists to
    catch.

    Returns (agree, worst_relative_difference) so a caller can report how
    close it came rather than only whether it passed.
    """
    a, b = path_periods(a_json), path_periods(b_json)
    if set(a) != set(b):
        return False, float("inf")
    worst = max((abs(a[k] - b[k]) / abs(a[k]) if a[k] else 0.0 for k in a), default=0.0)
    return worst <= reltol, worst


def summarize(design, rung_name, rung, metrics, results_dir):
    """Group the leaves by perturbation and reduce each to a spread."""
    spine = metrics.get(SPINE)
    if spine is None:
        raise RuntimeError(
            f"{design}/{rung_name}: the unperturbed spine did not produce a "
            "leaf, so there is nothing to compare the branches against"
        )

    def leaf(cid):
        return os.path.join(results_dir, f"{cid}.json")

    out = {}
    for name, spec in PERTURBATIONS.items():
        if not applicable(spec, rung):
            continue
        ids = [f"{name}@{v}" for v in spec["values"]]
        got = [(i, metrics[i]) for i in ids if metrics.get(i) is not None]
        if not got:
            out[name] = {
                "stage": spec["stage"],
                "kind": kind_of(spec, rung),
                "failed": True,
            }
            continue

        # The spine is included in every spread: the question is how far
        # the answer moves away from the unperturbed run, not how far the
        # perturbed runs sit from each other.
        periods = [critical_period(leaf(SPINE))] + [
            critical_period(leaf(i)) for i, _ in got
        ]
        errs = [spine["mean_rel_err"]] + [m["mean_rel_err"] for _, m in got]
        taus = [spine["kendall_tau"]] + [m["kendall_tau"] for _, m in got]
        recalls = [spine["worst_recall"]] + [m["worst_recall"] for _, m in got]

        agreements = [paths_agree(leaf(i), leaf(SPINE)) for i, _ in got]
        identical = all(ok for ok, _ in agreements)
        worst_rel = max((w for _, w in agreements), default=0.0)
        out[name] = {
            "stage": spec["stage"],
            "kind": kind_of(spec, rung),
            "knob": spec["knob"],
            "values": [i.split("@", 1)[1] for i, _ in got],
            "period": dispersion(periods),
            "mean_rel_err_span": max(errs) - min(errs),
            "kendall_tau_span": max(taus) - min(taus),
            "worst_recall_span": max(recalls) - min(recalls),
            # "unchanged to float32" rather than bit-identical: see
            # RELTOL. worst_rel is kept so a control that only just
            # passed is visible instead of rounded to a tick.
            "unchanged": identical,
            "worst_rel_diff": worst_rel,
            # Cost of having learnt this: the tail below the perturbed
            # stage, which is the whole point of the tree shape.
            "tail_s": statistics.fmean([m["runtime_s"] for _, m in got]),
        }
    return out


def verdict(design, per_stage):
    """Is the published front resolvable above this spread?

    Comparing two rungs is a two-sample comparison, not a comparison of
    two numbers.  Two independent draws differ with dispersion S*sqrt(2),
    so with k runs each a gap is resolvable only when

        gap  >=  z * S * sqrt(2/k)

    Reporting the raw span against the raw gap -- as an earlier version of
    this did -- drops both the sqrt(2) and the confidence factor and so
    overstates what one run per configuration can distinguish.

    S is a range rather than a standard deviation (see the module
    docstring), which makes this conservative: a range over a handful of
    epsilons overestimates a sigma, so k_needed is an upper bound.

    FRONT_GAP was fixed before the study ran, which is what makes either
    outcome meaningful.
    """
    gap = FRONT_GAP.get(design)
    if gap is None:
        return None
    # Constraint perturbations only.  A geometric nudge really does move
    # the floorplan, so scoring it against a ground truth measured at
    # epsilon zero mixes tool noise with a genuine change and would
    # overstate the spread.  A clock nudge changes nothing the metric can
    # see -- same netlist, same floorplan, and min_period subtracts the
    # constraint back out -- so its whole effect is noise, and it is the
    # only class this verdict may be built on.
    real = {
        name: info
        for name, info in per_stage.items()
        if info.get("kind") == "constraint" and not info.get("failed")
    }
    if not real:
        return None
    name, info = max(real.items(), key=lambda kv: kv[1]["mean_rel_err_span"])
    span = info["mean_rel_err_span"]
    mdd = Z * span * math.sqrt(2.0)
    return {
        "front_gap": gap,
        "worst_span": span,
        "worst_perturbation": name,
        "worst_stage": info["stage"],
        "min_detectable_diff": mdd,
        "resolvable_at_k1": mdd <= gap,
        "k_needed": (
            None if span == 0 else max(1, math.ceil(2.0 * (Z * span / gap) ** 2))
        ),
        "selection_bias": selection_bias(design, span),
    }


def selection_bias(design, span):
    """How much of the published best error could be selection alone.

    The front is the argmin of a noisy statistic over every configuration
    the sweep explored -- 238 of them on multiplier.  Taking the minimum
    of many near-tied noisy candidates biases the winner optimistically;
    for roughly Gaussian noise the expected best-of-N deviation grows like
    S*sqrt(2*ln N).  With N in the hundreds that factor is about 3.3, so
    the published best error can be optimistic by ~3 spans with no bug
    anywhere.  This is the same arithmetic as best-of-k, applied by
    accident instead of on purpose.

    It is an estimate, not a measurement: the proper fix is a validation
    split -- select the front under one perturbation and re-score it under
    a held-out one, so the reported number is not the one that was
    optimised.  That is the obvious follow-up and it is cheap given the
    tree.
    """
    n = N_EXPLORED.get(design)
    if not n or span == 0:
        return None
    return {
        "n_explored": n,
        "expected_optimism": span * math.sqrt(2.0 * math.log(n)),
    }


def check_null_controls(design, rung_name, per_stage):
    """The controls are checked, not reported and hoped over.

    A null control that fails means the harness is measuring something
    other than what it claims, and every other number in the section is
    then void -- so it is surfaced loudly rather than left in a table for
    a reader to notice.
    """
    broken = [
        name
        for name, info in per_stage.items()
        if info.get("kind") == "null_control"
        and not info.get("failed")
        and not info.get("unchanged")
    ]
    if broken:
        print(
            f"  !! NULL CONTROL FAILED ({design}/{rung_name}): {', '.join(broken)}\n"
            "     A clock nudge at a stage that reads no timing changed the\n"
            "     answer. Either a stage reads timing when we think it does\n"
            "     not, or the harness is not measuring what it claims. Every\n"
            "     other number for this rung is void until this is explained."
        )
    return not broken


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("estimator_exe")
    ap.add_argument("ground_truth_json")
    ap.add_argument("design_name")
    ap.add_argument("--rung", action="append", default=[], choices=sorted(RUNGS))
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument(
        "--subtree-timeout",
        type=float,
        default=1800.0,
        help="per-branch budget; a runaway branch loses only its subtree",
    )
    args = ap.parse_args()

    rungs = args.rung or ["cheap", "middle", "accurate"]
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    out_dir = os.path.join(ws, "test/estimation_ladder")
    unit = time_unit(args.ground_truth_json)

    report = {"design": args.design_name, "front_gap": FRONT_GAP.get(args.design_name)}
    ok = True
    for rung_name in rungs:
        rung = RUNGS[rung_name]
        manifest = build_manifest(rung, args.repeats)
        print(f"\n=== {args.design_name} / {rung_name}: {len(manifest)} leaves")
        # The leaf JSONs are needed only to reduce them to the summary
        # below, so they go to scratch rather than into the source tree --
        # and they are removed afterwards, since a stale directory from a
        # previous run makes run_estimator_batch's copytree fail.
        scratch = tempfile.mkdtemp(
            prefix=f"seed_{args.design_name}_{rung_name}_", dir=scratch_root()
        )
        keep = os.path.join(scratch, "leaves")
        try:
            metrics = run_estimator_batch(
                args.estimator_exe,
                manifest,
                args.ground_truth_json,
                parallel=True,
                subtree_timeout_s=args.subtree_timeout,
                keep_results_dir=keep,
            )
            per_stage = summarize(args.design_name, rung_name, rung, metrics, keep)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        ok = check_null_controls(args.design_name, rung_name, per_stage) and ok

        print(
            f"{'perturbation':>18s} {'stage':>14s} {'period range':>13s} "
            f"{'err span':>9s} {'tau span':>9s} {'tail s':>8s}"
        )
        for name, info in per_stage.items():
            if info.get("failed"):
                print(f"{name:>18s} {info['stage']:>14s}   (no leaf produced)")
                continue
            print(
                f"{name:>18s} {info['stage']:>14s} "
                f"{info['period']['range_pct']:>12.4f}% "
                f"{info['mean_rel_err_span']:>9.5f} "
                f"{info['kendall_tau_span']:>9.5f} "
                f"{info['tail_s']:>8.2f}"
            )
        report[rung_name] = {
            "rung": rung,
            "per_stage": per_stage,
            "spine": metrics[SPINE],
            "verdict": verdict(args.design_name, per_stage),
        }

    report["time_unit"] = unit
    report["null_controls_passed"] = ok
    path = os.path.join(out_dir, f"seed_sensitivity_{args.design_name}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(f"\nwrote {path}")
    if not ok:
        raise SystemExit("null control failed; see above")


if __name__ == "__main__":
    main()
