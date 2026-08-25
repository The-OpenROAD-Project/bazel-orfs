"""One knob at a time, everything else held fixed.

Most of what this study knows about individual knobs comes from an
Optuna archive, and that archive cannot answer a question about one
knob.  The sampler concentrates near the front, so a setting that
appears alongside good results may be causing them, riding along with
something else that is, or simply have been sampled more often where the
other knobs were already good.  Every "X doubles the failure rate" in
the earlier write-up is an association of that kind and was labelled as
one.

This is the other thing: a base configuration is held fixed, one knob
takes each of its values in turn, and the difference is attributable.
It is how the wire RC layer was measured, which produced the clearest
result in the study, and it is cheap -- a handful of runs per knob
rather than a sweep.

Knobs worth this treatment are the ones a person would actually reach
for and the study cannot currently answer:

  overflow        the Nesterov termination threshold, the single largest
                  runtime dial in global placement
  grt_iterations  how hard global routing tries
  repair_tns      how much of the endpoint list repair_timing works on;
                  at 0 it repaired one endpoint of 1943 and changed
                  nothing measurable, which says nothing about 50 or 100
  cts_dpl         CTS runs without legalising the placement first, but
                  whether that costs accuracy was never measured
  grt_flags       -use_cugr, -allow_congestion, -infinite_cap
"""

import argparse
import json
import os
import statistics

from estimation_metrics import compute_metrics, time_unit
from optuna_study import run_estimator

# Deep enough that the knobs under test all do something, cheap enough
# to run a dozen times per knob.
BASE = {
    "RUN_PLACE": "1",
    "RUN_MACRO_PLACE": "1",
    "RUN_GRT": "1",
    "GRT_ITERATIONS": "2",
}

# name -> (env overrides per value, values)
KNOBS = {
    "overflow": (
        lambda v: {"GP_ARGS": f"-overflow {v}"},
        ["0.05", "0.10", "0.15", "0.20", "0.30", "0.40"],
    ),
    "grt_iterations": (
        lambda v: {"GRT_ITERATIONS": v},
        ["1", "2", "5", "10", "20", "30"],
    ),
    "repair_tns": (
        lambda v: {
            "RUN_REPAIR_DESIGN": "1",
            "RUN_REPAIR_TIMING": "1",
            "REPAIR_TIMING_ARGS": f"-sequence {{vt_swap reroute}} -repair_tns {v}",
        },
        ["0", "25", "50", "100"],
    ),
    "cts_dpl": (
        lambda v: {"CLOCK_MODE": "real", "CTS_DPL": v},
        ["0", "1"],
    ),
    "grt_flags": (
        lambda v: {"GRT_ARGS": "" if v == "none" else f"-{v}"},
        ["none", "use_cugr", "allow_congestion", "infinite_cap"],
    ),
    "gpl_driven": (
        lambda v: {
            "GPL_TIMING_DRIVEN": "1" if v in ("timing", "both") else "0",
            "GPL_ROUTABILITY_DRIVEN": "1" if v in ("routability", "both") else "0",
        },
        ["neither", "timing", "routability", "both"],
    ),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("estimator_exe")
    ap.add_argument("ground_truth_json")
    ap.add_argument("design_name")
    ap.add_argument("--knob", action="append", default=[], choices=sorted(KNOBS))
    ap.add_argument("--wire-rc-layer", default=None)
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()

    knobs = args.knob or sorted(KNOBS)
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    out_dir = os.path.join(ws, "test/estimation_ladder")
    unit = time_unit(args.ground_truth_json)

    results = {}
    for knob in knobs:
        make_env, values = KNOBS[knob]
        print(f"\n=== {knob}")
        print(
            f"{'value':>16s} {'runtime':>9s} {'err':>8s} {'bias':>8s} "
            f"{'spread':>7s} {'tau':>8s} {'err_mac':>8s} {'tau_mac':>8s}"
        )
        rows = []
        for value in values:
            env = dict(BASE)
            env.update(make_env(value))
            if args.wire_rc_layer:
                env["WIRE_RC_LAYER_OVERRIDE"] = args.wire_rc_layer
            # Repeat only the runtime: accuracy is deterministic for a
            # given configuration, so repeating it would measure nothing.
            runtimes, metrics = [], None
            out_json = os.path.join(out_dir, f"knob_{knob}_{value}.json")
            try:
                for _ in range(max(1, args.repeats)):
                    run_estimator(
                        args.estimator_exe,
                        env,
                        args.ground_truth_json,
                        timeout_s=3600,
                        out_json=out_json,
                    )
                    metrics, _ = compute_metrics(args.ground_truth_json, out_json)
                    runtimes.append(metrics["runtime_s"])
            except Exception as exc:
                print(f"{value:>16s} FAILED {str(exc)[:60]}")
                continue
            finally:
                if os.path.exists(out_json):
                    os.remove(out_json)
            row = {
                "value": value,
                "runtime_s": statistics.median(runtimes),
                "mean_rel_err": metrics["mean_rel_err"],
                "bias": metrics["bias"],
                "spread": metrics["spread"],
                "kendall_tau": metrics["kendall_tau"],
                "mean_rel_err_macro": metrics.get("mean_rel_err_macro"),
                "kendall_tau_macro": metrics.get("kendall_tau_macro"),
            }
            rows.append(row)
            em = row["mean_rel_err_macro"]
            tm = row["kendall_tau_macro"]
            print(
                f"{value:>16s} {row['runtime_s']:8.1f}s {row['mean_rel_err']:8.4f} "
                f"{row['bias']:+8.4f} {row['spread']:7.4f} "
                f"{row['kendall_tau']:+8.3f} "
                f"{(f'{em:8.4f}' if em is not None else 'n/a'.rjust(8))} "
                f"{(f'{tm:+8.3f}' if tm is not None else 'n/a'.rjust(8))}"
            )
        results[knob] = rows

        # Say plainly whether the knob did anything, since a knob that
        # changes nothing is as much a result as one that helps and is
        # easier to overlook.
        if len(rows) > 1:
            errs = [r["mean_rel_err"] for r in rows]
            rts = [r["runtime_s"] for r in rows]
            best, worst = min(rows, key=lambda r: r["mean_rel_err"]), max(
                rows, key=lambda r: r["mean_rel_err"]
            )
            print(
                f"  error spans {min(errs):.4f} to {max(errs):.4f} "
                f"(best {best['value']}), runtime {min(rts):.1f}{'s'} to "
                f"{max(rts):.1f}s"
            )
            if max(errs) - min(errs) < 0.005:
                print(
                    "  -> changes accuracy by less than half a percentage "
                    "point across its whole range"
                )

    path = os.path.join(out_dir, f"knob_sweep_{args.design_name}.json")
    with open(path, "w") as f:
        json.dump(
            {"base": BASE, "wire_rc_layer": args.wire_rc_layer,
             "time_unit": unit, "knobs": results},
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
