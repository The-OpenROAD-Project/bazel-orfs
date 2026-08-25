"""Which layer should stand in for "an average wire"?

estimate_parasitics -placement turns a wirelength into a delay using the
resistance and capacitance that set_wire_rc installs, and set_wire_rc
takes those numbers from one nominated routing layer.  Which layer that
should be is a free parameter: a low layer is thin and resistive, a high
layer is wide and fast, and the wires the router actually builds are a
mixture that depends on the design.

That makes it the cheapest knob in the study -- it costs nothing at
runtime, it only changes an RC constant -- and the one aimed most
directly at the systematic optimism, since the estimator is optimistic
precisely because it mis-prices wire.

Unlike the sweep, this is a controlled experiment: one knob varies, the
rung is held fixed, and every layer is run on both designs.  The
knob-to-outcome associations elsewhere in this study come from a sampler
that concentrates near the front and confounds everything with
everything; this does not.
"""

import argparse
import json
import os

from estimation_metrics import compute_metrics
from optuna_study import run_estimator

# The rung to hold fixed. Global placement with a short global route: far
# enough up the ladder to have parasitics worth pricing, cheap enough to
# run once per layer per design.
BASE_RUNG = {
    "RUN_PLACE": "1",
    "RUN_MACRO_PLACE": "1",
    "RUN_GRT": "1",
    "GRT_ITERATIONS": "2",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("estimator_exe")
    ap.add_argument("ground_truth_json")
    ap.add_argument("design_name")
    ap.add_argument(
        "--layers",
        default="M1,M2,M3,M4,M5,M6,M7,M8,M9",
        help="comma-separated routing layers to nominate",
    )
    args = ap.parse_args()

    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    out_dir = os.path.join(ws, "test/estimation_ladder")
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    layers = ["(platform default)"] + args.layers.split(",")
    for layer in layers:
        env = dict(BASE_RUNG)
        if layer != "(platform default)":
            env["WIRE_RC_LAYER_OVERRIDE"] = layer
        out_json = os.path.join(out_dir, f"rc_{args.design_name}_{layer}.json")
        try:
            run_estimator(
                args.estimator_exe,
                env,
                args.ground_truth_json,
                timeout_s=3600,
                out_json=out_json,
            )
            metrics, _ = compute_metrics(args.ground_truth_json, out_json)
        except Exception as exc:
            print(f"{layer:20s} FAILED {str(exc)[:70]}")
            continue
        finally:
            if os.path.exists(out_json):
                os.remove(out_json)
        row = {"layer": layer}
        row.update(
            {
                k: metrics.get(k)
                for k in (
                    "mean_rel_err",
                    "bias",
                    "spread",
                    "kendall_tau",
                    "worst_recall",
                    "mean_rel_err_macro",
                    "kendall_tau_macro",
                    "runtime_s",
                )
            }
        )
        rows.append(row)
        print(
            f"{layer:20s} err {row['mean_rel_err']:.4f}  bias {row['bias']:+.4f}  "
            f"spread {row['spread']:.4f}  tau {row['kendall_tau']:+.3f}  "
            f"{row['runtime_s']:.1f}s"
        )

    path = os.path.join(out_dir, f"rc_sweep_{args.design_name}.json")
    with open(path, "w") as f:
        json.dump({"base_rung": BASE_RUNG, "rows": rows}, f, indent=2, sort_keys=True)
    print(f"\nWrote {path}")

    if rows:
        best = min(rows, key=lambda r: r["mean_rel_err"])
        default = next((r for r in rows if r["layer"] == "(platform default)"), None)
        print(f"best layer: {best['layer']} at {best['mean_rel_err']:.4f}")
        if default:
            gain = default["mean_rel_err"] - best["mean_rel_err"]
            print(
                f"platform default: {default['mean_rel_err']:.4f} "
                f"-- nominating {best['layer']} instead is worth {gain:+.4f} "
                f"for no runtime at all"
            )


if __name__ == "__main__":
    main()
