"""Capture ORFS's RC fit as data, so a figure can be drawn from it.

`make correlate_rc` prints a `setRC.tcl` body and an R-squared table to
stdout for a human to paste. That is fine for its intended use and no
use at all for a figure, so this calls the same functions ORFS's
correlateRC.py calls -- `read_segments_rc`, `fit_layer_models`,
`wire_rc_fit`, `compute_through_origin_fit_score` -- and writes the
result as JSON.

Deliberately not a reimplementation of the regression. A fitted value is
only comparable with the platform's if it came out of the same
procedure; the moment this file does its own arithmetic, every number it
produces becomes a new claim rather than a measurement.
"""

import argparse
import json
import os
import re
from pathlib import Path

from correlateRCHelper import (
    compute_through_origin_fit_score,
    fit_layer_models,
    read_segments_rc,
    wire_rc_fit,
)

# ORFS's own units for a platform setRC.tcl: kohm/um and ff/um. The
# scales are what correlateRC.py passes for `-res_unit kohm -cap_unit ff`.
RES_SCALE = 1.0e3
CAP_SCALE = 1.0e-15

_SET_LAYER_RC = re.compile(
    r"set_layer_rc\s+-layer\s+(\S+)\s+-resistance\s+(\S+)\s+-capacitance\s+(\S+)"
)
_SET_WIRE_RC = re.compile(
    r"set_wire_rc\s+-(signal|clock)\s+-resistance\s+(\S+)\s+-capacitance\s+(\S+)"
)


def platform_values(setrc_path):
    """The shipped per-layer table and blend, to compare the fit against."""
    layers, wire = {}, {}
    for line in Path(setrc_path).read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = _SET_LAYER_RC.search(stripped)
        if m and "-via" not in stripped:
            layers[m.group(1)] = {
                "resistance": float(m.group(2)),
                "capacitance": float(m.group(3)),
            }
        m = _SET_WIRE_RC.search(stripped)
        if m:
            wire[m.group(1)] = {
                "resistance": float(m.group(2)),
                "capacitance": float(m.group(3)),
            }
    if not layers:
        raise SystemExit("parsed no set_layer_rc rows out of %s" % setrc_path)
    return layers, wire


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--segments-rc", required=True, nargs="+")
    ap.add_argument("--platform-setrc", required=True)
    ap.add_argument("--out-json", required=True)
    args = ap.parse_args()

    routing_layers, layer_segments, layer_net_type_length = read_segments_rc(
        args.segments_rc
    )
    models = fit_layer_models(routing_layers, layer_segments)
    if not models:
        raise SystemExit(
            "no layer was fitted: the segments file has no routed segments, "
            "which is a missing measurement rather than a design with no RC"
        )

    plat_layers, plat_wire = platform_values(args.platform_setrc)

    fitted = {}
    for name, (res_model, cap_model, lengths, res, cap) in models.items():
        fitted[name] = {
            "resistance": res_model.coef_[0] / RES_SCALE,
            "capacitance": cap_model.coef_[0] * 1.0e-15 / CAP_SCALE,
            "res_r2": float(compute_through_origin_fit_score(res_model, lengths, res)),
            "cap_r2": float(compute_through_origin_fit_score(cap_model, lengths, cap)),
            "segments": len(res),
        }

    blend = {}
    for net_type in ("signal", "clock"):
        result = wire_rc_fit(
            models, layer_net_type_length, RES_SCALE, CAP_SCALE, [net_type]
        )
        if result:
            blend[net_type] = {"resistance": result[0], "capacitance": result[1]}

    out = Path(args.out_json)
    if not out.is_absolute():
        workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
        if workspace:
            out = Path(workspace) / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "fitted_layers": fitted,
                "fitted_wire_rc": blend,
                "platform_layers": plat_layers,
                "platform_wire_rc": plat_wire,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
