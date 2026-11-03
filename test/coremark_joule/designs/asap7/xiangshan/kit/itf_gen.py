#!/usr/bin/env python3
"""Write an interconnect technology file (ITF) for ASAP7.

ASAP7 is a predictive PDK and ships no ITF. This one is derived from what
the open flow already uses, so that another tool's extractor and OpenROAD see
the same wires:

  - widths, spacings and via cut sizes from the technology LEF;
  - resistance per unit length of each routing layer and of each via from
    the platform's setRC.tcl, the values OpenROAD estimates parasitics with;
    a layer's sheet resistance is that resistance times its minimum width;
  - thicknesses from the one assumption ASAP7's description makes for its
    BEOL: every metal at an aspect ratio of 2 (thickness twice the minimum
    width), and each dielectric between two metals as thick as the metal
    below it (ASPECT_RATIO, below);
  - each level's relative permittivity fitted so that a wire at minimum
    width, with neighbours at minimum spacing on both sides, has the
    capacitance per unit length setRC.tcl gives, under Sakurai and
    Tamaru's closed-form model (IEEE Trans. Electron Devices 30(2), 1983).

It is not a foundry deck. `--check` prints each layer's model R and C next
to setRC.tcl's.

  itf_gen.py --lef <tech.lef> --setrc <setRC.tcl> --out <asap7.itf>
"""

import argparse
import re
import sys

ASPECT_RATIO = 2.0
EPS0_FF_PER_UM = 8.854e-3
# a level with no capacitance in setRC.tcl (M1: the flow does not route
# on it) takes this permittivity, SiO2
ER_DEFAULT = 3.9
# oxide under M1, down to the device level
SUBSTRATE_UM = 0.1


def parse_lef(text):
    """Routing layers in order, bottom first: name, width, spacing; and the
    cut layers: name, cut area in um2."""
    layers = []
    cuts = {}
    for m in re.finditer(r"^LAYER\s+(\S+)\s*\n(.*?)^END\s+\1\s*$", text, re.M | re.S):
        name, body = m.group(1), m.group(2)
        kind = re.search(r"^\s*TYPE\s+(\w+)", body, re.M)
        if not kind:
            continue
        width = re.search(r"^\s*WIDTH\s+([\d.]+)\s*;", body, re.M)
        if kind.group(1) == "ROUTING" and re.match(r"^M\d+$", name):
            spacing = re.search(r"^\s*SPACING\s+([\d.]+)\s*;", body, re.M)
            if not width:
                raise SystemExit("itf_gen: routing layer %s has no WIDTH" % name)
            s = float(spacing.group(1)) if spacing else float(width.group(1))
            layers.append((name, float(width.group(1)), s))
        elif kind.group(1) == "CUT":
            # a square cut's WIDTH, else the first (single-cut) CUTCLASS
            cls = re.search(
                r"^\s*CUTCLASS\s+\S+\s+WIDTH\s+([\d.]+)\s+LENGTH\s+([\d.]+)", body, re.M
            )
            if width:
                cuts[name] = float(width.group(1)) ** 2
            elif cls:
                cuts[name] = float(cls.group(1)) * float(cls.group(2))
    if not layers:
        raise SystemExit("itf_gen: no routing layers in the LEF")
    return layers, cuts


def parse_setrc(text):
    """Per layer and per via: resistance in kohm/um (vias: kohm), and
    capacitance in fF/um, as set_layer_rc writes them."""
    rc = {}
    for m in re.finditer(r"set_layer_rc\s+(-layer|-via)\s+(\S+)\s+(.*)", text):
        args = m.group(3).split()
        values = dict(zip(args[::2], args[1::2]))
        rc[m.group(2)] = {k.lstrip("-"): float(v) for k, v in values.items()}
    return rc


def cap_per_um(er, w, s, t, h):
    """Sakurai and Tamaru: ground and two coupling neighbours, fF/um."""
    ground = 1.15 * (w / h) + 2.80 * (t / h) ** 0.222
    couple = (0.03 * (w / h) + 0.83 * (t / h) - 0.07 * (t / h) ** 0.222) * (
        s / h
    ) ** -1.34
    return er * EPS0_FF_PER_UM * (ground + 2.0 * couple)


def stack(layers, cuts, rc):
    """The levels, bottom first, each a dict the writer and the check use."""
    levels = []
    for i, (name, w, s) in enumerate(layers):
        if name not in rc or "resistance" not in rc[name]:
            raise SystemExit("itf_gen: setRC.tcl has no resistance for %s" % name)
        t = ASPECT_RATIO * w
        h = SUBSTRATE_UM if i == 0 else levels[-1]["t"]
        r_um = rc[name]["resistance"]
        c_um = rc[name].get("capacitance", 0.0)
        geometric = cap_per_um(1.0, w, s, t, h)
        er = c_um / geometric if c_um > 1e-6 else ER_DEFAULT
        levels.append(
            {
                "name": name,
                "w": w,
                "s": s,
                "t": t,
                "h": h,
                "er": er,
                "rpsq": r_um * 1000.0 * w,
                "r_um": r_um,
                "c_um": c_um,
            }
        )
    vias = []
    for lower, upper in zip(levels, levels[1:]):
        via = "V%s" % lower["name"].lstrip("M")
        if via not in rc or via not in cuts:
            raise SystemExit(
                "itf_gen: via %s between %s and %s not in setRC.tcl and the LEF"
                % (via, lower["name"], upper["name"])
            )
        vias.append(
            {
                "name": via,
                "from": lower["name"],
                "to": upper["name"],
                "rpv": rc[via]["resistance"] * 1000.0,
                "area": cuts[via],
            }
        )
    return levels, vias


def write_itf(levels, vias, out):
    lines = [
        "$ ASAP7 interconnect technology, derived by itf_gen.py from the",
        "$ technology LEF and the platform's setRC.tcl; not a foundry deck.",
        "$ Metal aspect ratio %.1f; permittivity per level fitted to setRC.tcl's"
        % ASPECT_RATIO,
        "$ capacitance at minimum width and spacing (Sakurai-Tamaru).",
        "",
        "TECHNOLOGY = asap7_kit",
        "GLOBAL_TEMPERATURE = 25.0",
        "",
    ]
    top = levels[-1]
    lines.append(
        "DIELECTRIC PASSIVATION {THICKNESS=%.4f ER=%.3f}" % (top["t"], top["er"])
    )
    for i in reversed(range(len(levels))):
        lv = levels[i]
        # the dielectric a conductor is embedded in is the one above it
        lines.append(
            "DIELECTRIC D_%s {THICKNESS=%.4f ER=%.3f}" % (lv["name"], lv["t"], lv["er"])
        )
        lines.append(
            "CONDUCTOR %s {THICKNESS=%.4f WMIN=%.4f SMIN=%.4f RPSQ=%.4f}"
            % (lv["name"], lv["t"], lv["w"], lv["s"], lv["rpsq"])
        )
        lines.append(
            "DIELECTRIC D_%s_below {THICKNESS=%.4f ER=%.3f}"
            % (lv["name"], lv["h"], lv["er"])
        )
    lines.append("")
    for v in vias:
        lines.append(
            "VIA %s {FROM=%s TO=%s RPV=%.3f AREA=%.6f}"
            % (v["name"], v["from"], v["to"], v["rpv"], v["area"])
        )
    out.write("\n".join(lines) + "\n")


def check(levels, out):
    out.write("layer  R model/setRC kohm/um   C model/setRC fF/um   ER\n")
    for lv in levels:
        r = lv["rpsq"] / 1000.0 / lv["w"]
        c = cap_per_um(lv["er"], lv["w"], lv["s"], lv["t"], lv["h"])
        out.write(
            "%-5s  %.5f %.5f   %.5f %.5f   %.3f\n"
            % (lv["name"], r, lv["r_um"], c, lv["c_um"], lv["er"])
        )


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--lef", required=True)
    p.add_argument("--setrc", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--check", action="store_true")
    a = p.parse_args(argv)
    with open(a.lef) as f:
        layers, cuts = parse_lef(f.read())
    with open(a.setrc) as f:
        rc = parse_setrc(f.read())
    levels, vias = stack(layers, cuts, rc)
    with open(a.out, "w") as f:
        write_itf(levels, vias, f)
    if a.check:
        check(levels, sys.stdout)


if __name__ == "__main__":
    main()
