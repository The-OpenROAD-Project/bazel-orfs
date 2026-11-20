#!/usr/bin/env python3
"""A block's extract dump (extract_block.tcl) as <block>.block.json.

The planner's per-block input: area and the outline the block's own flow
draws from it (die_rule), every port bus with its width and boundary
timing, and every hard object with its pins by side and the port buses
its pins reach. Schema:

  block, identity {dump, tool}
  clock {port, period_ps}
  area {std_um2, hard_um2, macros [{master, w, h, n}],
        die_rule {util, aspect, margin_um, core_w_um, core_h_um, w_um, h_um}}
  ports [{name, dir, bits, group, registered,
          in2reg_ps {max, bit}, reg2out_ps {max, bit},
          in2out [{to, max_ps, bits}]}]
  hard [{inst, master, kind, w, h, halo_um,
         pins {bus: {side, range, bits, layer}},
         nets [{pin, port, bits, via, depth}]}]

A port is registered when its worst boundary delay is at most what the
design names a register's own (--registered-in-ps, --registered-out-ps;
unnamed, registered is null) and it has no
combinational path through the block.

Stdlib only.
"""

import argparse
import hashlib
import json
import math
import re
import sys

TOOL = "block_json 1"


def parse(lines):
    """The dump's records, grouped by kind."""
    rec = {}
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue
        f = line.split("\t")
        rec.setdefault(f[0], []).append(f[1:])
    return rec


def group_of(bus):
    """A bus's group: its name without a trailing _<n> (io_in_0, io_in_1)."""
    return re.sub(r"_[0-9]+$", "", bus)


def bus_of(name):
    return re.sub(r"\[[0-9]+\]$", "", name)


def snap_up(v, step):
    return math.ceil(v / step - 1e-9) * step if step > 0 else v


def die_rule(var, std_um2, hard_um2, site):
    """The outline the block's flow draws: DIE_AREA when it is given, else
    the instance area over CORE_UTILIZATION at CORE_ASPECT_RATIO, the core
    snapped to sites and rows, plus CORE_MARGIN on every side."""
    if "DIE_AREA" in var:
        x0, y0, x1, y1 = [float(v) for v in var["DIE_AREA"].split()]
        return {
            "rule": "DIE_AREA",
            "w_um": round(x1 - x0, 3),
            "h_um": round(y1 - y0, 3),
        }
    if "CORE_UTILIZATION" not in var:
        return None
    util = float(var["CORE_UTILIZATION"]) / 100.0
    aspect = float(var.get("CORE_ASPECT_RATIO", 1.0))
    margin = float(var.get("CORE_MARGIN", 1.0))
    area = (std_um2 + hard_um2) / util
    cw = math.sqrt(area / aspect)
    ch = cw * aspect
    cw = snap_up(cw, site[0])
    ch = snap_up(ch, site[1])
    return {
        "rule": "CORE_UTILIZATION",
        "util": util,
        "aspect": aspect,
        "margin_um": margin,
        "core_w_um": round(cw, 3),
        "core_h_um": round(ch, 3),
        "w_um": round(cw + 2 * margin, 3),
        "h_um": round(ch + 2 * margin, 3),
    }


def build(rec, dump_hash, reg_in_ps, reg_out_ps):
    var = {k: v for k, v in rec.get("var", [])}
    # the block flow's own macro halo: half its macro placer's minimum
    # channel, the larger of the two
    halo_um = (
        max([float(v) for v in var.get("RTLMP_MIN_CHANNEL_SIZE", "0").split()] or [0.0])
        / 2
    )
    site = [float(v) for v in rec["site"][0]] if "site" in rec else [0, 0]
    std = float(rec["area"][0][0]) if "area" in rec else 0.0
    hard = []
    masters = {}
    for inst, master, w, h, kind in rec.get("hard", []):
        w, h = float(w), float(h)
        hard.append(
            {
                "inst": inst,
                "master": master,
                "kind": kind,
                "w": w,
                "h": h,
                "halo_um": halo_um,
                "pins": {},
                "nets": [],
            }
        )
        masters.setdefault(master, {"master": master, "w": w, "h": h, "n": 0})["n"] += 1
    by_inst = {h["inst"]: h for h in hard}
    for inst, bus, side, lo, hi, bits, layer in rec.get("hpin", []):
        by_inst[inst]["pins"][bus] = {
            "side": side,
            "range": [float(lo), float(hi)],
            "bits": int(bits),
            "layer": layer,
        }
    for inst, pin, port, bits, via, depth in rec.get("hnet", []):
        by_inst[inst]["nets"].append(
            {
                "pin": pin,
                "port": port,
                "bits": int(bits),
                "via": via,
                "depth": int(depth),
            }
        )
    hard_um2 = sum(h["w"] * h["h"] for h in hard)

    ports = {}
    for name, d in rec.get("port", []):
        b = bus_of(name)
        p = ports.setdefault(
            b,
            {
                "name": b,
                "dir": "in" if d == "input" else ("out" if d == "output" else d),
                "bits": 0,
                "group": group_of(b),
            },
        )
        p["bits"] += 1
    for bus, ps, bit in rec.get("in2reg", []):
        ports[bus]["in2reg_ps"] = {"max": float(ps), "bit": bit}
    for bus, ps, bit in rec.get("reg2out", []):
        ports[bus]["reg2out_ps"] = {"max": float(ps), "bit": bit}
    for bus, to, ps, bits in rec.get("in2out", []):
        ports[bus].setdefault("in2out", []).append(
            {"to": to, "max_ps": float(ps), "bits": int(bits)}
        )
    for p in ports.values():
        if p["dir"] == "in":
            t = p.get("in2reg_ps", {}).get("max", 0.0)
            p["registered"] = (
                None if reg_in_ps is None else (t <= reg_in_ps and not p.get("in2out"))
            )
        elif p["dir"] == "out":
            t = p.get("reg2out_ps", {}).get("max", math.inf)
            fed = any(
                o["to"] == p["name"]
                for q in ports.values()
                for o in q.get("in2out", [])
            )
            p["registered"] = (
                None if reg_out_ps is None else (t <= reg_out_ps and not fed)
            )
    clock = None
    if "clock" in rec:
        clock = {"port": rec["clock"][0][0], "period_ps": float(rec["clock"][0][1])}
    return {
        "block": rec["block"][0][0],
        "identity": {"dump": "sha256:" + dump_hash, "tool": TOOL},
        "clock": clock,
        "area": {
            "std_um2": round(std, 3),
            "hard_um2": round(hard_um2, 3),
            "macros": sorted(masters.values(), key=lambda m: m["master"]),
            "die_rule": die_rule(var, std, hard_um2, site),
        },
        "ports": sorted(ports.values(), key=lambda p: p["name"]),
        "hard": hard,
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("dump", help="extract_block.tcl's dump")
    ap.add_argument("out", help="the block.json to write")
    ap.add_argument("--registered-in-ps", type=float)
    ap.add_argument("--registered-out-ps", type=float)
    args = ap.parse_args(argv)
    with open(args.dump, "rb") as f:
        raw = f.read()
    rec = parse(raw.decode().splitlines())
    out = build(
        rec,
        hashlib.sha256(raw).hexdigest(),
        args.registered_in_ps,
        args.registered_out_ps,
    )
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
