"""The seed-sensitivity study's null control, as a test.

est_measure_paths reports min_period = clk_period - slack, so loosening
the clock by eps also loosens every slack by eps and the two cancel: a
clock-period nudge cannot move the reported metric except by causing a
timing-driven stage to take a different branch.  Apply it at a stage that
reads no timing -- floorplan, or place_pins -- and the answer must come
back unchanged, path for path.

Unchanged, not bit-identical.  The cancellation is exact in real
arithmetic and only float32-exact in the tool: OpenSTA keeps both
clk_period and slack in a 32-bit float, so a nudge leaves a residue of
order float32 epsilon times the period -- ~6e-5 on a 1000ps clock,
8.8e-8 relative.  Measured, a 1ps nudge moves all 54 sampled paths by
that much and a 10ps nudge moves only 5, because 1010 is exactly
representable in float32 and 1001 is not.  That is arithmetic, so the
comparison is to RELTOL and the study's resolution floor is ~1e-7
relative -- three orders below the front gaps it is used to judge.

That is the guard the whole study rests on, which is why it is a test
rather than a line in a table.  A perturbation that silently failed to
apply would satisfy every accuracy check in the study and then report a
spread of exactly zero everywhere: the one wrong answer that looks
like a clean result.  est_perturb_clock reads the period back and errors
if the nudge did not land; this checks the other half, that a nudge which
*did* land changes nothing where nothing should change.

It also exercises something this harness gets for free nowhere else.  The
branches are forked copy-on-write children, threads do not survive
fork(), and OpenSTA and OpenROAD respawn their worker pools inside the
child -- so "a forked child computes what the parent would have computed"
is an assumption worth testing rather than assuming.  Both perturbed
branches and a plain repeat of the spine are run here, so a difference
between fork and inline execution shows up as a failure.
"""

import os
import sys

from optuna_study import run_estimator_batch
from seed_sensitivity import RELTOL, RUNGS, SPINE, paths_agree, path_periods

# A rung with no timing-driven stage at all: no -timing_driven placement,
# no CTS, no repair, no global route.  Nothing in it reads a clock
# constraint, so the nudge below has nothing legitimate to act through.
RUNG = dict(RUNGS["cheap"])

# 10ps as well as 1ps: if 1ps alone came back identical it could be that
# the nudge is below some internal quantum rather than that the stage
# ignores timing, and a control that can pass for the wrong reason is not
# a control.
NUDGES = {
    "floorplan@1": {"CLK_PERIOD_EPS_FLOORPLAN": "1"},
    "floorplan@10": {"CLK_PERIOD_EPS_FLOORPLAN": "10"},
    "pins@1": {"CLK_PERIOD_EPS_PINS_PRE": "1"},
    "pins@10": {"CLK_PERIOD_EPS_PINS_PRE": "10"},
    # An explicit zero is inert -- est_perturb_clock returns early -- but
    # it differs from the spine as a grouping key, so the walk forks and
    # re-runs the stages.  That makes this leaf a genuine repeat rather
    # than a second write of the spine's own result.
    "repeat": {"CLK_PERIOD_EPS_FLOORPLAN": "0"},
}


def main():
    estimator_exe, ground_truth = sys.argv[1], sys.argv[2]
    results_dir = os.path.join(os.environ.get("TEST_TMPDIR", "."), "leaves")

    manifest = {SPINE: dict(RUNG)}
    for name, knobs in NUDGES.items():
        manifest[name] = dict(RUNG, **knobs)

    metrics = run_estimator_batch(
        estimator_exe,
        manifest,
        ground_truth,
        parallel=True,
        keep_results_dir=results_dir,
    )

    missing = [cid for cid, m in metrics.items() if m is None]
    if missing:
        sys.exit(f"branches produced no leaf: {missing}")

    spine_json = os.path.join(results_dir, f"{SPINE}.json")
    n_paths = len(path_periods(spine_json))
    failures = []
    for name in NUDGES:
        ok, worst_rel = paths_agree(
            os.path.join(results_dir, f"{name}.json"), spine_json
        )
        if not ok:
            failures.append(
                f"{name}: worst path differs by {worst_rel:.3e} relative, "
                f"above the {RELTOL:.0e} float32 allowance"
            )
        else:
            print(
                f"ok  {name}: all {n_paths} paths agree with the spine "
                f"(worst {worst_rel:.2e} relative)"
            )

    if failures:
        sys.exit(
            "null control failed:\n  "
            + "\n  ".join(failures)
            + "\n\nA clock nudge at a stage that reads no timing changed the\n"
            "answer, or a forked branch disagreed with the spine. Either way\n"
            "the seed-sensitivity numbers do not mean what they claim until\n"
            "this is explained."
        )
    print(f"\nnull control holds across {len(NUDGES)} branches")


if __name__ == "__main__":
    main()
