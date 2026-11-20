#!/usr/bin/env python3
"""A platform's extract dump (extract_pdk.tcl) as pdk.json.

Per routing layer: direction, pitch, track density, unit RC, and the
optimally repeated wire: the buffer and repeater spacing that minimise
delay per micron over the dump's (buffer, length) samples, each sample
the resizer's own buffer-into-wire-into-buffer delay. Per pin layer the
pins per micron of edge one layer holds, 1 / (pitch * min_tracks *
margin). Schema:

  platform, identity {dump, tool}
  site [w, h], io {H: [layers], V: [layers]}, routing [min, max]
  pin_rule {min_tracks, margin}
  layers {name: {dir, pitch_um, width_um, tracks_per_um, r_ohm_per_um,
          c_ff_per_um, ps_per_um, spacing_um, buffer, pins_per_um,
          unrepeated [[length_um, ps], ...], via_ps, routable}}
  vias {cut: r_ohm}

via_ps is the delay of a via stack from the lowest pin layer up to the
layer and down again, driving one repeater segment's wire capacitance.

Stdlib only.
"""

import argparse
import hashlib
import json
import sys

TOOL = "pdk_json 1"


def parse(lines):
    """The dump's records by kind; "seq" keeps layers and vias in the
    technology's order."""
    rec = {"seq": []}
    for line in lines:
        line = line.rstrip("\n")
        if line:
            f = line.split("\t")
            rec.setdefault(f[0], []).append(f[1:])
            if f[0] in ("layer", "via"):
                rec["seq"].append((f[0], f[1]))
    return rec


def cuts_above(seq):
    """Per routing layer the cut layer right above it."""
    out = {}
    last = None
    for kind, name in seq:
        if kind == "layer":
            last = name
        elif last is not None and last not in out:
            out[last] = name
    return out


def best_repeater(samples):
    """(ps_per_um, spacing_um, buffer) minimising delay per micron."""
    best = None
    for buf, length, ps in samples:
        if length <= 0:
            continue
        k = ps / length
        if best is None or k < best[0]:
            best = (k, length, buf)
    return best


def build(rec, dump_hash, min_tracks, margin):
    layers = {}
    order = []
    for name, d, pitch, width, r, c in rec.get("layer", []):
        pitch = float(pitch)
        layers[name] = {
            "dir": d,
            "pitch_um": pitch,
            "width_um": float(width),
            "tracks_per_um": round(1.0 / pitch, 4) if pitch > 0 else 0.0,
            "r_ohm_per_um": float(r),
            "c_ff_per_um": float(c),
            "pins_per_um": (
                round(1.0 / (pitch * min_tracks * margin), 4) if pitch > 0 else 0.0
            ),
        }
        order.append(name)
    vias = {cut: float(r) for cut, r in rec.get("via", [])}
    samples = {}
    for layer, buf, length, ps in rec.get("wire", []):
        samples.setdefault(layer, []).append((buf, float(length), float(ps)))
    for name, s in samples.items():
        k, spacing, buf = best_repeater(s)
        L = layers[name]
        L["ps_per_um"] = round(k, 5)
        L["spacing_um"] = spacing
        L["buffer"] = buf
        L["unrepeated"] = sorted([[l, ps] for b, l, ps in s if b == buf])
    io_h, io_v = rec["io"][0] if "io" in rec else ("", "")
    io = {"H": io_h.split(), "V": io_v.split()}
    lo, hi = rec["range"][0] if "range" in rec else (order[0], order[-1])
    routable = (
        order[order.index(lo) : order.index(hi) + 1]
        if lo in order and hi in order
        else order
    )
    pin_layers = [n for n in io["H"] + io["V"] if n in layers]
    base = min((order.index(n) for n in pin_layers), default=0)
    above = cuts_above(rec["seq"])
    for i, name in enumerate(order):
        L = layers[name]
        L["routable"] = name in routable
        stack = [above[n] for n in order[min(base, i) : max(base, i)] if n in above]
        r = sum(vias[c] for c in stack)
        seg_c = L["c_ff_per_um"] * L.get("spacing_um", 0.0)
        L["via_ps"] = round(2 * r * seg_c * 1e-3, 4)
    site = [float(v) for v in rec["site"][0]] if "site" in rec else None
    return {
        "platform": rec["platform"][0][0] if "platform" in rec else "",
        "identity": {"dump": "sha256:" + dump_hash, "tool": TOOL},
        "site": site,
        "io": io,
        "routing": [lo, hi],
        "pin_rule": {"min_tracks": min_tracks, "margin": margin},
        "layers": layers,
        "order": order,
        "vias": vias,
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump")
    ap.add_argument("out")
    ap.add_argument(
        "--min-tracks",
        type=float,
        default=2.0,
        help="tracks per pin: a pin and the track left beside it",
    )
    ap.add_argument(
        "--margin",
        type=float,
        default=1.5,
        help="pin margin, test/macro_select's calibration",
    )
    args = ap.parse_args(argv)
    with open(args.dump, "rb") as f:
        raw = f.read()
    out = build(
        parse(raw.decode().splitlines()),
        hashlib.sha256(raw).hexdigest(),
        args.min_tracks,
        args.margin,
    )
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
