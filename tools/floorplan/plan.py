#!/usr/bin/env python3
"""Screen a macro cut for a floorplan, cheapest check first; plan it when it fits.

Inputs, all JSON: one <block>.block.json per macro (extract_block.tcl,
block_json.py), the parent's crossings (parent.json, extract_parent.tcl),
the platform's wire model (pdk.json, extract_pdk.tcl), the cut (which
block each macro is) and the constraints. The macros and the parent's
own logic (the glue, one soft region filling the free space) are placed
by pin_plan's analytic placer unless the constraints place them; every
interface bus goes to the side of its macro facing its partner. Then the
rungs, cheapest first; the first that fails stops the plan:

  a pins_per_um   per macro side, the bits on it over its length against
                  the pins one pin layer holds (pdk.json); over one layer
                  is debt, over `pin_layers` does not fit
  b area          each macro's outline from its own flow's rule
                  (die_rule) against its slot; the outlines, the glue at
                  its density and the channels against the die
  c aspect        each outline's aspect against its range, and its
                  shortest side against its largest hard object
  d internal      each macro's hard objects (memories, register files,
                  macros) rough-placed inside its outline behind a
                  pin-access band on every side that carries pins;
                  where they cannot be, the band gives and the objects
                  wall the side: a pin side whose free share is under
                  `free_fraction` is blocked; objects that do not fit at
                  all have no arrangement
  e channels      bits crossing each channel against its tracks per layer
  f path budget   each register-to-register chain across macros against
                  the period on its assigned layer

The verdict (verdict.json, verdict.md) names the failed constraint with
its excess, block, side and bus, the buses that contribute, and the
remedies; on a feasible cut, floorplan.json holds the die, each macro's
place, outline and pin ranges per bus, for the flows (floorplan.bzl).

Coordinates in every output are ORFS's: microns, origin lower left.

Stdlib only.
"""

import argparse
import copy
import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pin_plan as P  # noqa: E402

TOOL = "plan 1"
GLUE = "GLUE"
RUNGS = [
    "pins_per_um",
    "area",
    "aspect",
    "internal_arrangement",
    "channel_capacity",
    "path_budget",
]
DEFAULTS = {
    "channel_um": 4.0,
    "pin_layers": 2,
    "free_fraction": 0.5,
    "pin_access_um": 10.0,
    "glue_density": 0.5,
    "std_density": 0.7,
    "aspect_range": [1 / 6, 6.0],
    "usable": 0.5,
    "gcell_limit": 1.0,
    "setup_ps": 30.0,
    "skew_ps": 50.0,
    "congestion_k": 1.0,
    "feedthrough_depth": 3,
    "die_slack": [1.15, 1.3, 1.5, 1.75, 2.0, 2.5, 3.0],
}


def read_json(path):
    with open(path) as f:
        return json.load(f)


def sha(obj):
    return (
        "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()
    )


class Model:
    """Macros with their outlines and buses, the glue, the nets between them."""

    def __init__(self, blocks, parent, pdk, cut, constraints):
        self.blocks = {b["block"]: b for b in blocks}
        self.parent = parent or {}
        self.pdk = pdk
        self.cut = cut
        self.c = dict(DEFAULTS, **constraints)
        # the router's grid resolves the narrowest channel the placer leaves,
        # at most 250 gcells a side (route_bundles)
        self.gcell_given = "gcell_um" in self.c
        self.c.setdefault("gcell_um", self.c["channel_um"] / 2)
        self.macros = {}
        for m, spec in sorted(cut["macros"].items()):
            block = spec["block"] if isinstance(spec, dict) else spec
            if block not in self.blocks:
                raise SystemExit(
                    "plan: macro %s names block %s, which has no block.json"
                    % (m, block)
                )
            self.macros[m] = {
                "block": block,
                "inst": spec.get("inst") if isinstance(spec, dict) else None,
            }
        self.nets = self._nets()
        self.glue_um2 = float(
            self.c.get("glue_um2", self.parent.get("glue", {}).get("std_um2", 0.0))
        )

    def block(self, m):
        return self.blocks[self.macros[m]["block"]]

    def macro_of(self, block, inst=None):
        """The macro a crossing's end is: by its instance (the cut's `inst`,
        else a macro of that name), else by its block."""
        if inst not in (None, "", "-"):
            for m, v in self.macros.items():
                if v["inst"] == inst:
                    return m
            if inst in self.macros:
                return inst
        for m, v in self.macros.items():
            if v["block"] == block:
                return m
        return None

    def _nets(self):
        """(a, a_bus, b, b_bus, bits, a_bits, b_bits) per interface, one per
        pair of buses. From parent.json's crossings when it is given (a
        crossing through a register of the parent's is two nets, each to the
        glue); else every port bus of every macro to the glue."""
        nets = {}

        def add(a, ab, b, bb, na, nb):
            k = (a, ab, b, bb)
            old = nets.get(k, (0, 0))
            nets[k] = (max(old[0], na), max(old[1], nb))

        if self.parent.get("crossings") is not None:
            for x in self.parent["crossings"]:
                a = self.macro_of(x["a"], x.get("a_inst")) or GLUE
                b = self.macro_of(x["b"], x.get("b_inst")) or GLUE
                if a == b:
                    continue
                na = x.get("a_bits", x["bits"])
                nb = x.get("b_bits", x["bits"])
                if x.get("via") == "reg" and GLUE not in (a, b):
                    add(a, x["a_bus"], GLUE, "", na, na)
                    add(GLUE, "", b, x["b_bus"], nb, nb)
                else:
                    add(a, x["a_bus"], b, x.get("b_bus", ""), na, nb)
        else:
            for m in self.macros:
                for p in self.block(m)["ports"]:
                    add(m, p["name"], GLUE, "", p["bits"], p["bits"])
        return [
            (a, ab, b, bb, max(na, nb), na, nb)
            for (a, ab, b, bb), (na, nb) in sorted(nets.items())
        ]

    def outline_area(self, m):
        """The area of the outline the macro's own flow draws; its slot's
        when its flow names no rule."""
        r = self.block(m)["area"]["die_rule"]
        if r is None:
            slot = self.macro_c(m).get("slot")
            if slot is None:
                raise SystemExit(
                    "plan: %s's block.json has no die_rule (its flow sets neither DIE_AREA nor "
                    "CORE_UTILIZATION) and the constraints give it no slot" % m
                )
            return slot[0] * slot[1]
        return r["w_um"] * r["h_um"]

    def hard(self, m):
        return self.block(m).get("hard", [])

    def macro_c(self, m):
        return self.c.get("macros", {}).get(m, {})

    def ppu(self, side):
        """Pins per um of one layer on a side: E and W edges carry the
        horizontal pin layer."""
        io = self.pdk["io"]["H" if side in "EW" else "V"]
        layers = self.pdk["layers"]
        return min(layers[n]["pins_per_um"] for n in io) if io else 1.0

    def pin_layer(self, side):
        io = self.pdk["io"]["H" if side in "EW" else "V"]
        return io[0] if io else ""

    def tech(self):
        """pin_plan's tech from pdk.json: the pin layers' pitch, the routing
        layers' track density per direction."""
        io = self.pdk["io"]
        layers = self.pdk["layers"]
        density = {"H": 0.0, "V": 0.0}
        for n, cap in self.layer_tracks().items():
            density[layers[n]["dir"]] += cap
        rule = self.pdk["pin_rule"]
        return {
            "pitch_um": {
                "H": layers[io["H"][0]]["pitch_um"] if io["H"] else 0.1,
                "V": layers[io["V"][0]]["pitch_um"] if io["V"] else 0.1,
            },
            "min_tracks": rule["min_tracks"],
            "margin": rule["margin"],
            "track_density_per_um": min(density.values()),
            "track_density_h_per_um": density["H"],
            "track_density_v_per_um": density["V"],
            "usable": self.c["usable"],
        }

    def layer_tracks(self):
        """Tracks per um the parent's routes get per routable layer: the
        layer's density times its share (constraints `layers`: what the
        power grid and the router's own routes leave, 1 by default)."""
        shares = self.c.get("layers", {})
        out = {}
        for n, L in self.pdk["layers"].items():
            if L.get("routable"):
                out[n] = L["tracks_per_um"] * shares.get(n, {}).get("share", 1.0)
        return out


def shape_options(model, m):
    """(w, h) outlines a macro may take: its slot when the constraints give
    one, else its flow's outline area at every aspect in range that holds
    its largest hard object."""
    mc = model.macro_c(m)
    if "slot" in mc:
        return [tuple(mc["slot"])]
    area = model.outline_area(m)
    lo, hi = mc.get("aspect_range", model.c["aspect_range"])
    aspects = mc.get("aspects", P.ASPECTS)
    hw = max([h["w"] for h in model.hard(m)] or [0])
    hh = max([h["h"] for h in model.hard(m)] or [0])
    out = []
    for r in aspects:
        if not lo - 1e-9 <= r <= hi + 1e-9:
            continue
        w, h = math.sqrt(area / r), math.sqrt(area * r)
        if w >= hw and h >= hh:
            out.append(r)
    return out or [1.0]


def start_aspect(model, m, options):
    """The aspect closest to square whose long side holds the macro's
    widest interface (its bits to one partner) at the pin layers' limit:
    where the aspect search starts, since a side too short for one
    interface cannot be fixed by moving one macro at a time."""
    per_partner = {}
    for a, _, b, _, bits, _, _ in model.nets:
        if a == m:
            per_partner[b] = per_partner.get(b, 0) + bits
        elif b == m:
            per_partner[a] = per_partner.get(a, 0) + bits
    need = max(per_partner.values() or [0]) / (
        min(model.ppu("N"), model.ppu("E")) * model.c["pin_layers"]
    )
    area = model.outline_area(m)
    best = None
    for r in options or [1.0]:
        long_side = max(math.sqrt(area / r), math.sqrt(area * r))
        key = (long_side < need, abs(math.log(r)), r)
        if best is None or key < best[0]:
            best = (key, r)
    return best[1]


def pin_plan_input(model, die=None, aspects=None, forbidden=None):
    """The pin_plan plan for the model."""
    pp = {
        "tech": model.tech(),
        "growth": 1.0,
        "util": 1.0,
        "channel_um": model.c["channel_um"],
        "gcell_um": model.c["gcell_um"],
        "macros": {},
        "nets": [],
        "macro_aspects": {},
        "forced_sides": {},
        "forbidden_sides": forbidden or {},
        "die_slack": model.c["die_slack"],
        "pin_layers": model.c["pin_layers"],
    }
    for m in model.macros:
        mc = model.macro_c(m)
        if "slot" in mc:
            pp["macros"][m] = {"fixed_shape": list(mc["slot"])}
        else:
            pp["macros"][m] = {"std_um2": model.outline_area(m)}
            pp["macro_aspects"][m] = shape_options(model, m)
        if mc.get("sides"):
            pp["forced_sides"][m] = dict(mc["sides"])
    pp["start_aspects"] = {
        m: start_aspect(model, m, pp["macro_aspects"][m]) for m in pp["macro_aspects"]
    }
    pp["macros"][GLUE] = {
        "soft": True,
        "whitespace": True,
        "std_um2": model.glue_um2 / model.c["glue_density"],
    }
    for a, _, b, _, bits, _, _ in model.nets:
        pp["nets"].append([a, b, bits])
    if die:
        pp["die"] = {"w": die[0], "h": die[1]}
    return pp


def to_down(r, die_h):
    """ORFS (lower-left origin) to pin_plan's frame (y down)."""
    return [r[0], die_h - r[1] - r[3], r[2], r[3]]


def to_up(r, die_h):
    return [
        round(r[0], 3),
        round(die_h - r[1] - r[3], 3),
        round(r[2], 3),
        round(r[3], 3),
    ]


def layouts(model, forbidden=None, aspects_override=None):
    """pin_plan's plan and the candidate layouts, best first: [(die, rects in
    pin_plan's frame)], empty when no legal placement exists. With the die
    and every macro's place given there is one; else the die search's best
    few, so a later rung can pass over a layout the placer liked."""
    die = model.c.get("die")
    pp = pin_plan_input(model, die, forbidden=forbidden)
    places = {
        m: model.macro_c(m)["place"]
        for m in model.macros
        if "place" in model.macro_c(m)
    }
    if places and not die:
        raise SystemExit("plan: constraints place macros but give no die")
    if die:
        die = tuple(die)
        fixed = {}
        for m, xy in places.items():
            w, h = (
                model.macro_c(m).get("slot")
                or P.shapes_for(pp, aspects_override or {})[m]
            )
            fixed[m] = to_down([xy[0], xy[1], w, h], die[1])
        pp["fixed"] = fixed
        if len(places) == len(model.macros):
            return pp, [(die, fixed)]
        if aspects_override is not None:
            q = P.quick(pp, aspects_override, die)
            return pp, ([(die, q[1])] if q else [])
        aspects, q = P.tune_aspects(pp, dict(pp["start_aspects"]), die)
        return pp, ([(die, q[1])] if q else [])
    return pp, solve_die(pp, aspects_override)


def solve_die(pp, aspects_override=None, keep=6):
    """Dies from pin_plan's search, each with its legal placement at the
    tuned aspects: the smallest holding every edge within the pin layers
    first, then by emptiest fullest edges; `keep` of them."""
    hard, soft = P.need_area(pp, P.shapes_for(pp, {}))
    cands = []
    fits_at = None
    for i, slack in enumerate(pp["die_slack"]):
        for ar in (1.0, 1.25, 0.8, 1.5, 0.67):
            area = (hard + soft) * slack
            die = (math.sqrt(area / ar), math.sqrt(area * ar))
            p = dict(pp, die={"w": die[0], "h": die[1]})
            if aspects_override is not None:
                q = P.quick(p, aspects_override, die)
            else:
                _, q = P.tune_aspects(p, pp["start_aspects"], die, passes=1)
            if q is None:
                continue
            over = q[0][0][0] > pp["pin_layers"]
            cands.append(
                ((over, q[0][0] if over else (), die[0] * die[1], q[0]), die, q[1])
            )
            if not over and fits_at is None:
                fits_at = i
        # one slack past the first that fits, for the later rungs to choose
        if fits_at is not None and i > fits_at:
            break
    cands.sort(key=lambda c: c[0])
    return [(die, rects) for _, die, rects in cands[:keep]]


def bus_contributors(model, m, partner):
    """The macro's buses to a partner, widest first."""
    out = []
    for a, ab, b, bb, _, na, nb in model.nets:
        if a == m and b == partner:
            out.append({"bus": ab, "bits": na, "partner": partner, "partner_bus": bb})
        elif b == m and a == partner:
            out.append({"bus": bb, "bits": nb, "partner": partner, "partner_bus": ab})
    ports = {p["name"]: p for p in model.block(m)["ports"]}
    merged = {}
    for o in out:
        k = (o["bus"], o["partner"])
        if k in merged:
            merged[k]["bits"] = max(merged[k]["bits"], o["bits"])
        else:
            merged[k] = dict(o)
            p = ports.get(o["bus"])
            if p is not None:
                merged[k]["registered"] = p.get("registered")
    return sorted(merged.values(), key=lambda o: (-o["bits"], o["bus"]))


def edge_report(model, edges):
    """Per (macro, side): bits, length, pins per um, layers needed, buses."""
    out = []
    for (m, s), e in sorted(edges.items()):
        if m not in model.macros:
            continue
        ppu1 = model.ppu(s)
        per_um = e["need"] / e["len"] if e["len"] else math.inf
        contributors = []
        for partner, bits, lo, hi in e["bundles"]:
            for c in bus_contributors(model, m, partner):
                if c not in contributors:
                    contributors.append(c)
        contributors.sort(key=lambda c: (-c["bits"], c["bus"]))
        out.append(
            {
                "macro": m,
                "block": model.macros[m]["block"],
                "side": s,
                "bits": e["need"],
                "um": round(e["len"], 3),
                "per_um": round(per_um, 3),
                "limit_one_layer": round(ppu1, 3),
                "layers": per_um / ppu1 if ppu1 else math.inf,
                "contributors": contributors,
                "segments": [[o, n, lo, hi] for o, n, lo, hi in e["bundles"]],
            }
        )
    return out


def rung_a(model, edges):
    findings = []
    n = model.c["pin_layers"]
    for e in edge_report(model, edges):
        if e["layers"] <= 1.0:
            continue
        status = "fail" if e["layers"] > n * (1 + 1e-3) else "debt"
        lim1 = e["limit_one_layer"]
        findings.append(
            {
                "rung": "pins_per_um",
                "status": status,
                "block": e["block"],
                "macro": e["macro"],
                "side": e["side"],
                "bus": e["contributors"][0]["bus"] if e["contributors"] else "",
                "demand": {"bits": e["bits"], "um": e["um"], "per_um": e["per_um"]},
                "limit": {
                    "one_layer": lim1,
                    "layers": n,
                    "all_layers": round(lim1 * n, 3),
                },
                "excess": {
                    "bits": max(0, round(e["bits"] - e["um"] * lim1 * n)),
                    "factor": round(e["per_um"] / (lim1 * n), 3),
                },
                "contributors": e["contributors"][:8],
            }
        )
    return findings


def rung_b(model, rects, die):
    findings = []
    for m in model.macros:
        need = model.outline_area(m)
        r = model.block(m)["area"]["die_rule"]
        slot = model.macro_c(m).get("slot")
        if slot and slot[0] * slot[1] + 1e-6 < need:
            findings.append(
                {
                    "rung": "area",
                    "status": "fail",
                    "block": model.macros[m]["block"],
                    "macro": m,
                    "need": {
                        "w": r["w_um"],
                        "h": r["h_um"],
                        "um2": round(need, 1),
                        "rule": rule_text(r),
                    },
                    "slot": {
                        "w": slot[0],
                        "h": slot[1],
                        "um2": round(slot[0] * slot[1], 1),
                    },
                    "excess_um2": round(need - slot[0] * slot[1], 1),
                }
            )
    if rects is None:
        hard = sum(model.outline_area(m) for m in model.macros)
        soft = model.glue_um2 / model.c["glue_density"]
        f = {
            "rung": "area",
            "status": "fail",
            "block": "die",
            "macro": None,
            "need": {
                "um2": round(hard + soft, 1),
                "macros_um2": round(hard, 1),
                "glue_um2": round(soft, 1),
            },
        }
        if die:
            f["die"] = {"w": die[0], "h": die[1], "um2": round(die[0] * die[1], 1)}
            f["excess_um2"] = round(hard + soft - die[0] * die[1], 1)
        f["reason"] = "no legal placement of the macros with their channels in the die"
        findings.append(f)
    return findings


def rule_text(r):
    if r.get("rule") == "DIE_AREA":
        return "DIE_AREA"
    return "CORE_UTILIZATION %g + CORE_MARGIN %g" % (100 * r["util"], r["margin_um"])


def rung_c(model, rects):
    findings = []
    for m in model.macros:
        w, h = rects[m][2], rects[m][3]
        mc = model.macro_c(m)
        # a slot is the shape the constraints chose; only a range they
        # name for the macro itself is checked against it
        default = [0, math.inf] if "slot" in mc else model.c["aspect_range"]
        lo, hi = mc.get("aspect_range", default)
        a = h / w
        hw = max([o["w"] for o in model.hard(m)] or [0])
        hh = max([o["h"] for o in model.hard(m)] or [0])
        if not lo - 1e-6 <= a <= hi + 1e-6:
            findings.append(
                {
                    "rung": "aspect",
                    "status": "fail",
                    "block": model.macros[m]["block"],
                    "macro": m,
                    "aspect": round(a, 3),
                    "range": [lo, hi],
                    "shape": [round(w, 3), round(h, 3)],
                }
            )
        elif w + 1e-6 < hw or h + 1e-6 < hh:
            findings.append(
                {
                    "rung": "aspect",
                    "status": "fail",
                    "block": model.macros[m]["block"],
                    "macro": m,
                    "aspect": round(a, 3),
                    "shape": [round(w, 3), round(h, 3)],
                    "largest_hard": [hw, hh],
                    "reason": "shortest side under the largest hard object",
                }
            )
    return findings


# --- rung d: the hard objects inside each macro --------------------------------


def pack(objs, region, base):
    """Shelf-pack objects (dicts with w, h, halo_um) into region [x, y, w, h]
    (ORFS frame), shelves parallel to the `base` side and stacked away from
    it, tallest first; objects keep their halo from each other, not from
    the region's edge. A list of [x, y, w, h] in the order of objs, or None."""
    rx, ry, rw, rh = region
    if rw <= 0 or rh <= 0:
        return None
    # work in a frame where the base side is S: u along it, v away from it
    along = rw if base in "NS" else rh
    depth = rh if base in "NS" else rw
    order = sorted(
        range(len(objs)),
        key=lambda i: (-dims(objs[i], base)[1], -dims(objs[i], base)[0], i),
    )
    out = [None] * len(objs)
    v = 0.0
    u = 0.0
    shelf_h = 0.0
    first_in_shelf = True
    for i in order:
        ou, ov = dims(objs[i], base)
        gap = 2 * objs[i].get("halo_um", 0.0)
        start = u if first_in_shelf else u + gap
        if start + ou > along + 1e-6:
            v += shelf_h + gap
            u, shelf_h, first_in_shelf = 0.0, 0.0, True
            start = 0.0
        if start + ou > along + 1e-6 or v + ov > depth + 1e-6:
            return None
        out[i] = from_frame(start, v, ou, ov, region, base)
        u = start + ou
        shelf_h = max(shelf_h, ov)
        first_in_shelf = False
    return out


def dims(o, base):
    """(along, depth) of an object for shelves on `base`."""
    return (o["w"], o["h"]) if base in "NS" else (o["h"], o["w"])


def from_frame(u, v, ou, ov, region, base):
    rx, ry, rw, rh = region
    if base == "S":
        return [rx + u, ry + v, ou, ov]
    if base == "N":
        return [rx + u, ry + rh - v - ov, ou, ov]
    if base == "W":
        return [rx + v, ry + u, ov, ou]
    return [rx + rw - v - ov, ry + u, ov, ou]


def free_spans(w, h, side, rects, depth, halo):
    """Spans of a side with no object (and its halo) within `depth` of it."""
    length = w if side in "NS" else h
    covered = []
    for r in rects:
        near = {
            "S": r[1] - halo < depth,
            "N": h - (r[1] + r[3]) - halo < depth,
            "W": r[0] - halo < depth,
            "E": w - (r[0] + r[2]) - halo < depth,
        }[side]
        if near:
            a, b = (r[0], r[0] + r[2]) if side in "NS" else (r[1], r[1] + r[3])
            covered.append([max(0.0, a - halo), min(length, b + halo)])
    covered.sort()
    merged = []
    for a, b in covered:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    free, cur = [], 0.0
    for a, b in merged:
        if a > cur:
            free.append([cur, a])
        cur = max(cur, b)
    if cur < length:
        free.append([cur, length])
    return free, merged


def pin_demand(model, m, edges):
    """Bits per side of a macro."""
    return {s: e["need"] for (n, s), e in edges.items() if n == m}


def pull_side(model, m, obj, edges):
    """The side carrying most of the bits of the ports a hard object's
    pins reach."""
    ports = {n["port"] for n in obj.get("nets", [])}
    best = {}
    for (n, s), e in edges.items():
        if n != m:
            continue
        for partner, bits, lo, hi in e["bundles"]:
            for c in bus_contributors(model, m, partner):
                if c["bus"] in ports:
                    best[s] = best.get(s, 0) + c["bits"]
    if not best:
        return None
    return max(sorted(best), key=lambda s: best[s])


def arrange(model, m, w, h, edges):
    """The rough placement of a macro's hard objects in its w x h outline:
    (rects, walled sides, relaxed bands) or None when they do not fit."""
    objs = model.hard(m)
    margin = (
        model.block(m)["area"]["die_rule"].get("margin_um", 1.0)
        if model.block(m)["area"]["die_rule"]
        else 1.0
    )
    core = [margin, margin, w - 2 * margin, h - 2 * margin]
    demand = pin_demand(model, m, edges)
    d = model.c["pin_access_um"]
    pin_sides = sorted(
        [s for s, b in demand.items() if b > 0], key=lambda s: (demand[s], s)
    )
    pulls = {}
    for o in objs:
        s = pull_side(model, m, o, edges)
        if s:
            pulls[s] = pulls.get(s, 0) + 1
    bases = sorted("NSEW", key=lambda s: (-pulls.get(s, 0), -demand.get(s, 0), s))
    # bands give way on the least-loaded pin side first
    relax_orders = [[]] + [pin_sides[:k] for k in range(1, len(pin_sides) + 1)]
    halo = max([o.get("halo_um", 0.0) for o in objs] or [0.0])
    for relaxed in relax_orders:
        # a band keeps an object's halo pin_access_um from the outline
        band = {
            s: (
                0.0
                if s in relaxed or s not in pin_sides
                else max(0.0, d + halo - margin)
            )
            for s in "NSEW"
        }
        region = [
            core[0] + band["W"],
            core[1] + band["S"],
            core[2] - band["W"] - band["E"],
            core[3] - band["S"] - band["N"],
        ]
        for base in bases:
            rects = pack(objs, region, base)
            if rects is not None:
                return rects, relaxed, base
    return None


def rung_d(model, rects, edges):
    findings = []
    internal = {}
    floor = model.c["free_fraction"]
    for m in sorted(model.macros):
        objs = model.hard(m)
        if not objs:
            continue
        w, h = rects[m][2], rects[m][3]
        blk = model.block(m)
        hard_um2 = sum(
            (o["w"] + 2 * o.get("halo_um", 0)) * (o["h"] + 2 * o.get("halo_um", 0))
            for o in objs
        )
        std_um2 = blk["area"]["std_um2"] / model.c["std_density"]
        if hard_um2 + std_um2 > w * h + 1e-6:
            findings.append(
                {
                    "rung": "internal_arrangement",
                    "status": "fail",
                    "kind": "no_internal_arrangement",
                    "block": blk["block"],
                    "macro": m,
                    "slot": [round(w, 3), round(h, 3)],
                    "need_um2": round(hard_um2 + std_um2, 1),
                    "slot_um2": round(w * h, 1),
                    "objects": [o["inst"] for o in objs][:20],
                }
            )
            continue
        res = arrange(model, m, w, h, edges)
        if res is None:
            findings.append(
                {
                    "rung": "internal_arrangement",
                    "status": "fail",
                    "kind": "no_internal_arrangement",
                    "block": blk["block"],
                    "macro": m,
                    "slot": [round(w, 3), round(h, 3)],
                    "need_um2": round(hard_um2 + std_um2, 1),
                    "slot_um2": round(w * h, 1),
                    "objects": [o["inst"] for o in objs][:20],
                    "largest": max([[o["w"], o["h"]] for o in objs]),
                }
            )
            continue
        placed, relaxed, base = res
        halo = max([o.get("halo_um", 0) for o in objs] or [0])
        demand = pin_demand(model, m, edges)
        rows = []
        for o, r in zip(objs, placed):
            rows.append(
                {
                    "inst": o["inst"],
                    "place": [round(r[0], 3), round(r[1], 3)],
                    "shape": [o["w"], o["h"]],
                    "walls": [],
                }
            )
        for s in "NSEW":
            free, walls = free_spans(w, h, s, placed, model.c["pin_access_um"], halo)
            length = w if s in "NS" else h
            free_um = sum(b - a for a, b in free)
            for o, r, row in zip(objs, placed, rows):
                span = (r[0], r[0] + r[2]) if s in "NS" else (r[1], r[1] + r[3])
                if any(a < span[1] and span[0] < b for a, b in walls) and s in relaxed:
                    row["walls"].append(s)
            bits = demand.get(s, 0)
            if not bits:
                continue
            frac = free_um / length if length else 0.0
            ppu1 = model.ppu(s)
            per_um_free = bits / free_um if free_um > 0 else math.inf
            limit = ppu1 * model.c["pin_layers"]
            if frac < floor or per_um_free > limit:
                walling = [
                    {
                        "inst": o["inst"],
                        "span": [
                            round(max(0, (r[0] if s in "NS" else r[1]) - halo), 3),
                            round(
                                (r[0] + r[2] if s in "NS" else r[1] + r[3]) + halo, 3
                            ),
                        ],
                    }
                    for o, r, row in zip(objs, placed, rows)
                    if s in row["walls"]
                ]
                needing = []
                for (n, side), e in edges.items():
                    if n == m and side == s:
                        for partner, b, lo, hi in e["bundles"]:
                            for c in bus_contributors(model, m, partner):
                                needing.append(
                                    {
                                        "bus": c["bus"],
                                        "bits": c["bits"],
                                        "partner": partner,
                                    }
                                )
                findings.append(
                    {
                        "rung": "internal_arrangement",
                        "status": "fail",
                        "kind": "side_blocked",
                        "block": blk["block"],
                        "macro": m,
                        "side": s,
                        "free_um": round(free_um, 3),
                        "of_um": round(length, 3),
                        "free_fraction": round(frac, 3),
                        "floor": floor,
                        "walls": walling,
                        "buses_needing": sorted(needing, key=lambda c: -c["bits"])[:8],
                        "bus": needing[0]["bus"] if needing else "",
                        "pins_per_um_on_free": (
                            round(per_um_free, 3) if free_um > 0 else None
                        ),
                        "limit": round(limit, 3),
                    }
                )
        internal[m] = rows
    return findings, internal


# --- rung e: channels -----------------------------------------------------------


def channel_name(model, rects, die, direction, cx, cy):
    """The two macros (or the die edge) either side of a gcell across its
    wires' direction: a horizontal wire's channel runs between macros
    above and below it."""
    hard = [(n, r) for n, r in rects.items() if n in model.macros]
    if direction == "h":
        lo = [
            (cy - (r[1] + r[3]), n)
            for n, r in hard
            if r[0] <= cx <= r[0] + r[2] and r[1] + r[3] <= cy
        ]
        hi = [
            (r[1] - cy, n) for n, r in hard if r[0] <= cx <= r[0] + r[2] and r[1] >= cy
        ]
    else:
        lo = [
            (cx - (r[0] + r[2]), n)
            for n, r in hard
            if r[1] <= cy <= r[1] + r[3] and r[0] + r[2] <= cx
        ]
        hi = [
            (r[0] - cx, n) for n, r in hard if r[1] <= cy <= r[1] + r[3] and r[0] >= cx
        ]
    a = min(lo)[1] if lo else "die"
    b = min(hi)[1] if hi else "die"
    return "|".join(sorted([a, b]))


def route_bundles(model, pp, rects, edges, die):
    """Each bundle between two hard macros routed on the gcell grid through
    the parent's free space (pin_plan's router): [(a, b, bits, kind,
    length_um, cells)] and the grid with its demand."""
    g = model.c["gcell_um"]
    if not model.gcell_given:
        g = max(g, max(die) / 250.0)
    pp = dict(pp, gcell_um=g)
    grid = P.Grid(pp, rects, die)
    out = []
    done = set()
    # a chunk is the bits whose pins span one gcell of edge, so its wires
    # spread as the pins do
    chunk = model.c.get("route_chunk_bits") or max(
        1, int(min(model.ppu("N"), model.ppu("E")) * model.c["pin_layers"] * grid.g)
    )
    for me, other, n, q in sorted(
        P.bundles(pp, rects), key=lambda t: (-t[2], t[0], t[1])
    ):
        if P.is_soft(pp, other):
            continue
        key = tuple(sorted((me, other)))
        if key in done:
            continue
        done.add(key)
        sa = P.choose_side(pp, rects, me, rects[other], other)
        sb = P.choose_side(pp, rects, other, rects[me], me)
        pa = P.pin_point(rects, edges, me, sa, other)
        pb = P.pin_point(rects, edges, other, sb, me)
        manhattan = abs(pa[0] - pb[0]) + abs(pa[1] - pb[1])
        if (
            P.OPP[sa] == sb
            and P.gap_between(rects[me], rects[other]) <= pp["channel_um"] + 1e-6
        ):
            out.append((me, other, n, "facing", manhattan, manhattan, []))
            continue
        nch = max(1, int(math.ceil(n / chunk)))
        paths = []
        for k in range(nch):
            f = (k + 0.5) / nch
            qa = P.pin_point(rects, edges, me, sa, other, f)
            qb = P.pin_point(rects, edges, other, sb, me, f)
            paths.append(
                grid.route(
                    grid.cell(qa, sa), grid.cell(qb, sb), min(chunk, n - k * chunk)
                )
            )
        if any(p is None for p in paths):
            out.append((me, other, n, "no_channel", None, manhattan, []))
            continue
        cells = sorted({c for p in paths for c in p})
        length = max(len(p) for p in paths) * grid.g
        out.append((me, other, n, "channel", max(length, manhattan), manhattan, cells))
    return out, grid


def rung_e(model, st):
    """Bundles that find no path through free space, and the channels whose
    demand is over their tracks."""
    pp, rects, die, edges = st["pp"], st["rects"], st["die"], st["edges"]
    routes, grid = route_bundles(model, pp, rects, edges, die)
    st["routes"] = routes
    st["grid"] = grid
    findings = []
    for a, b, bits, kind, length, manhattan, cells in routes:
        if kind == "no_channel":
            buses = bus_contributors(model, a, b)
            findings.append(
                {
                    "rung": "channel_capacity",
                    "status": "fail",
                    "kind": "no_channel",
                    "block": model.macros[a]["block"],
                    "macro": a,
                    "partner": b,
                    "bits": bits,
                    "bus": buses[0]["bus"] if buses else "",
                    "contributors": buses[:8],
                    "reason": "no path through the parent's free space: the route would cross a macro",
                }
            )
    limit = model.c["gcell_limit"]
    tracks = model.layer_tracks()
    worst = {}
    for direction, use, cap in (("h", grid.h, grid.cap_h), ("v", grid.v, grid.cap_v)):
        for (i, j), d in use.items():
            if cap <= 0 or d <= cap * limit:
                continue
            cx, cy = (i + 0.5) * grid.g, (j + 0.5) * grid.g
            name = channel_name(model, rects, die, direction, cx, cy)
            k = (name, direction)
            if k not in worst or d / cap > worst[k][0]:
                worst[k] = (d / cap, d, cap, (i, j))
    # a channel between macros first: a gcell with the die edge on both
    # sides is a corner the route turns in, the channels beside it say more
    order = sorted(
        worst.items(), key=lambda kv: (kv[0][0] == "die|die", -kv[1][0], kv[0])
    )
    for (name, direction), (util, d, cap, cell) in order:
        through = []
        for a, b, bits, kind, length, manhattan, cells in routes:
            if cell in cells:
                through.append(
                    {
                        "a": a,
                        "b": b,
                        "bits": bits,
                        "buses": [c["bus"] for c in bus_contributors(model, a, b)][:4],
                    }
                )
        layer_dir = "H" if direction == "h" else "V"
        per_layer = {
            n: round(t * model.c["usable"] * grid.g, 1)
            for n, t in sorted(tracks.items())
            if model.pdk["layers"][n]["dir"] == layer_dir
        }
        macros = [x for x in name.split("|") if x != "die"]
        findings.append(
            {
                "rung": "channel_capacity",
                "status": "fail",
                "kind": "over_capacity",
                "channel": name,
                "direction": direction,
                "block": model.macros[macros[0]]["block"] if macros else "die",
                "side": None,
                "demand_tracks": round(d, 1),
                "capacity_tracks": round(cap, 1),
                "utilisation": round(util, 3),
                "gcell_um": grid.g,
                "capacity_per_layer": per_layer,
                "bus": (
                    through[0]["buses"][0] if through and through[0]["buses"] else ""
                ),
                "routes": through[:8],
            }
        )
    return findings


# --- rung f: the path budget across boundaries ----------------------------------


def layer_pairs(model):
    """Routing layer pairs, lowest first: (name, ps_per_um, via_ps, layers),
    a pair's delay the slower of its two layers' repeated wire."""
    L = model.pdk["layers"]
    order = [
        n for n in model.pdk["order"] if L[n].get("routable") and L[n].get("ps_per_um")
    ]
    pairs = []
    for i in range(0, len(order), 2):
        group = order[i : i + 2]
        pairs.append(
            (
                "/".join(group),
                max(L[n]["ps_per_um"] for n in group),
                max(L[n].get("via_ps", 0.0) for n in group),
                group,
            )
        )
    return pairs


def period_ps(model):
    if "period_ps" in model.c:
        return float(model.c["period_ps"])
    for b in model.blocks.values():
        if b.get("clock"):
            return b["clock"]["period_ps"]
    raise SystemExit(
        "plan: no period: no block has a clock and the constraints give no period_ps"
    )


def port(model, m, bus):
    for p in model.block(m)["ports"]:
        if p["name"] == bus:
            return p
    return None


def crossings_from(model, m, bus):
    """The parent's crossings leaving a macro's output bus: (to macro or
    GLUE, to bus, via, glue_ps)."""
    out = []
    for x in model.parent.get("crossings", []):
        a = model.macro_of(x["a"], x.get("a_inst"))
        if a != m or x["a_bus"] != bus:
            continue
        b = model.macro_of(x["b"], x.get("b_inst")) or GLUE
        out.append(
            (b, x["b_bus"], x.get("via", "wire"), x.get("glue_ps", 0.0), x["bits"])
        )
    return out


def chains(model):
    """Register-to-register paths whose ends are in different macros, as
    legs: the source's reg2out, the parent's own delay (a parent register
    ends a chain), feedthrough macros' in2out, the destination's in2reg.
    Each [(kind, macro, bus, ps)], with the hops between macros."""
    out = []

    def walk(legs, hops, m, bus, depth):
        for b, bbus, via, glue_ps, bits in crossings_from(model, m, bus):
            if b == GLUE or via == "reg":
                continue
            p = port(model, b, bbus)
            if p is None:
                continue
            nl = legs + [("glue", GLUE, "", glue_ps)] if glue_ps else list(legs)
            nh = hops + [(m, b, bits)]
            if "in2reg_ps" in p:
                out.append((nl + [("in2reg", b, bbus, p["in2reg_ps"]["max"])], nh))
            if depth < model.c["feedthrough_depth"]:
                for ft in p.get("in2out", []):
                    walk(
                        nl + [("in2out", b, bbus + "->" + ft["to"], ft["max_ps"])],
                        nh,
                        b,
                        ft["to"],
                        depth + 1,
                    )

    for m in sorted(model.macros):
        for p in model.block(m)["ports"]:
            if p["dir"] == "out" and "reg2out_ps" in p:
                walk(
                    [("reg2out", m, p["name"], p["reg2out_ps"]["max"])],
                    [],
                    m,
                    p["name"],
                    0,
                )
    return out


def hop_route(st, a, b):
    """(length um, congestion utilisation) of the planned route between
    two macros: rung e's route, else the Manhattan distance between their
    centres."""
    for x, y, bits, kind, length, manhattan, cells in st.get("routes", []):
        if {x, y} == {a, b}:
            util = 0.0
            grid = st.get("grid")
            for c in cells:
                for use, cap in ((grid.h, grid.cap_h), (grid.v, grid.cap_v)):
                    if cap > 0:
                        util = max(util, use.get(c, 0) / cap)
            return (length if length is not None else manhattan), util, cells
    ra, rb = st["rects"][a], st["rects"][b]
    (ax, ay), (bx, by) = P.center(ra), P.center(rb)
    return abs(ax - bx) + abs(ay - by), 0.0, []


def rung_f(model, st):
    """Each chain against the period: the wire's share is what the logic
    legs leave less setup and skew; the lowest layer pair whose repeated
    wire fits it is the chain's; the bits each upper pair takes on a
    route against that pair's tracks in the route's corridor."""
    period = period_ps(model)
    setup, skew = model.c["setup_ps"], model.c["skew_ps"]
    k = model.c["congestion_k"]
    pairs = layer_pairs(model)
    tracks = model.layer_tracks()
    findings = []
    assigned = {}
    worst = []
    for legs, hops in chains(model):
        logic = sum(ps for _, _, _, ps in legs)
        budget = period - setup - skew - logic
        length = 0.0
        util = 0.0
        hop_cells = []
        for a, b, bits in hops:
            ln, u, cells = hop_route(st, a, b)
            length += ln
            util = max(util, u)
            hop_cells.append((a, b, bits, cells, ln))
        congestion = 1.0 + k * max(0.0, util - 1.0)
        name = " -> ".join(
            ["%s.%s" % (legs[0][1], legs[0][2])] + ["%s" % b for _, b, _ in hops]
        )
        dest = legs[-1]
        chain = "%s.%s -> %s.%s" % (legs[0][1], legs[0][2], dest[1], dest[2])
        row = {
            "chain": chain,
            "legs": [
                {"kind": kd, "at": at, "bus": bus, "ps": round(ps, 1)}
                for kd, at, bus, ps in legs
            ],
            "margins": {"setup": setup, "skew": skew},
            "period_ps": period,
            "wire_budget_ps": round(budget, 1),
            "bits": min(bits for _, _, bits in hops),
        }
        if budget < 0:
            dom = max(legs, key=lambda l: l[3])
            row.update(
                {
                    "status": "fail",
                    "layer_needed": "none closes",
                    "slack_ps": round(budget, 1),
                    "dominates": "%s %s.%s" % (dom[0], dom[1], dom[2]),
                    "reason": "the logic alone is over the period",
                }
            )
            worst.append(row)
            continue
        choice = None
        for pname, ps_um, via, group in pairs:
            wire = ps_um * length * congestion + via
            if wire <= budget:
                choice = (pname, ps_um, via, wire, group)
                break
        top = pairs[-1]
        if choice is None:
            wire = top[1] * length * congestion + top[2]
            row.update(
                {
                    "status": "fail",
                    "layer_needed": "none closes",
                    "route": {
                        "length_um": round(length, 1),
                        "layer": top[0],
                        "ps_per_um": top[1],
                        "via_ps": top[2],
                        "congestion": round(congestion, 3),
                        "wire_ps": round(wire, 1),
                    },
                    "slack_ps": round(budget - wire, 1),
                    "max_distance_um": round(
                        max(0.0, budget - top[2]) / (top[1] * congestion), 1
                    ),
                    "dominates": "wire" if wire > max(l[3] for l in legs) else "logic",
                }
            )
            worst.append(row)
            continue
        pname, ps_um, via, wire, group = choice
        row.update(
            {
                "status": "ok",
                "layer_needed": pname,
                "route": {
                    "length_um": round(length, 1),
                    "layer": pname,
                    "ps_per_um": ps_um,
                    "via_ps": via,
                    "congestion": round(congestion, 3),
                    "wire_ps": round(wire, 1),
                },
                "slack_ps": round(budget - wire, 1),
            }
        )
        worst.append(row)
        if pname != pairs[0][0]:
            for a, b, bits, cells, ln in hop_cells:
                key = (tuple(sorted((a, b))), pname)
                entry = assigned.setdefault(
                    key,
                    {
                        "bits": 0,
                        "chains": [],
                        "cells": cells,
                        "len": ln,
                        "group": group,
                    },
                )
                entry["bits"] += bits
                entry["chains"].append(chain)
    for row in worst:
        if row["status"] == "fail":
            dest = row["legs"][-1]
            src = row["legs"][0]
            findings.append(
                dict(
                    row,
                    rung="path_budget",
                    block=model.macros[dest["at"]]["block"],
                    macro=dest["at"],
                    bus=dest["bus"],
                    side=None,
                    source={"macro": src["at"], "bus": src["bus"]},
                )
            )
    g = st["grid"].g if st.get("grid") else model.c["gcell_um"]
    for ((a, b), pname), e in sorted(assigned.items()):
        steps = max(1.0, e["len"] / g)
        corridor = max(1.0, len(e["cells"]) / steps)
        cap = (
            corridor
            * g
            * sum(tracks.get(n, 0.0) for n in e["group"])
            * model.c["usable"]
        )
        if e["bits"] > cap:
            findings.append(
                {
                    "rung": "path_budget",
                    "status": "fail",
                    "kind": "layer_capacity",
                    "block": model.macros[a]["block"],
                    "macro": a,
                    "partner": b,
                    "side": None,
                    "channel": "%s|%s" % (a, b),
                    "layers": pname,
                    "demand_tracks": e["bits"],
                    "capacity_tracks": round(cap, 1),
                    "bus": e["chains"][0].split(" -> ")[0].split(".", 1)[1],
                    "chains": e["chains"][:8],
                    "reason": "the chains that close only on %s need more of its tracks than the route has"
                    % pname,
                }
            )
    st["chains"] = sorted(worst, key=lambda r: r["slack_ps"])
    return findings


# --- the plan -------------------------------------------------------------------


def evaluate(model, forbidden=None):
    """Lay out and run the rungs; the state the verdict and the floorplan
    are written from. Of the candidate layouts the first that every rung
    passes, else the one that gets furthest."""
    pp, cands = layouts(model, forbidden)
    best = None
    for die, rects in cands:
        p = dict(pp, die={"w": die[0], "h": die[1]})
        st = evaluate_layout(model, p, rects, die)
        stop = first_stop(st["findings"])
        rank = RUNGS.index(stop) if stop else len(RUNGS)
        if best is None or rank > best[0]:
            best = (rank, st)
        if stop is None:
            break
    if best is None:
        return evaluate_layout(model, pp, None, model.c.get("die"))
    return best[1]


def evaluate_layout(model, pp, rects, die):
    st = {
        "pp": pp,
        "rects": rects,
        "die": die,
        "findings": [],
        "internal": {},
        "edges": None,
    }
    if rects is not None:
        edges = P.assign(pp, rects)
        st["edges"] = edges
        st["findings"] += rung_a(model, edges)
    st["findings"] += rung_b(model, rects, die)
    if rects is None:
        return st
    st["findings"] += rung_c(model, rects)
    fd, internal = rung_d(model, rects, st["edges"])
    st["findings"] += fd
    st["internal"] = internal
    st["findings"] += rung_e(model, st)
    st["findings"] += rung_f(model, st)
    return st


def plan(model, passes=3):
    """Evaluate, and between passes move the buses off a side the hard
    objects block unless the constraints force it."""
    forbidden = {}
    st = evaluate(model, forbidden)
    for _ in range(passes - 1):
        blocked = [
            f
            for f in st["findings"]
            if f.get("kind") == "side_blocked"
            and not model.macro_c(f["macro"]).get("sides")
        ]
        if not blocked:
            break
        changed = False
        for f in blocked:
            s = forbidden.setdefault(f["macro"], [])
            if f["side"] not in s and len(s) < 3:
                s.append(f["side"])
                changed = True
        if not changed:
            break
        st = evaluate(model, forbidden)
    st["forbidden"] = forbidden
    return st


def first_stop(findings, rungs=RUNGS):
    for r in rungs:
        for f in findings:
            if f["rung"] == r and f["status"] == "fail":
                return r
    return None


def remedies_for(f):
    """The remedy kinds that address a finding."""
    k = f.get("kind", f["rung"])
    return {
        "pins_per_um": [
            "reshape",
            "resize_slot",
            "split_side",
            "narrow_bus",
            "move_module",
        ],
        "area": ["resize_slot", "resize_die"],
        "aspect": ["reshape"],
        "side_blocked": ["change_side", "reshape", "move_memory", "move_slot"],
        "no_internal_arrangement": ["resize_slot", "reshape", "move_memory"],
        "no_channel": ["move_slot", "resize_die", "change_side"],
        "over_capacity": ["move_slot", "resize_die", "narrow_bus", "promote_layer"],
        "path_budget": ["register_bus", "move_slot", "promote_layer", "move_module"],
        "layer_capacity": ["narrow_bus", "register_bus", "move_slot"],
    }.get(k, [])


def verdict(model, st, identity, run_all=False):
    findings = st["findings"]
    stop = first_stop(findings)
    if not run_all and stop is not None:
        idx = RUNGS.index(stop)
        findings = [f for f in findings if f["rung"] in RUNGS[: idx + 1]]
    for f in findings:
        if f["status"] == "fail":
            f["remedies"] = remedies_for(f)
    die = st["die"]
    internal = {}
    for m, rows in st["internal"].items():
        internal[m] = rows
    return {
        "identity": identity,
        "verdict": "feasible" if stop is None else "infeasible",
        "stopped_at": stop,
        "die": [round(die[0], 3), round(die[1], 3)] if die else None,
        "findings": findings,
        "remedies": [],
        "internal_placement": internal,
        "forbidden_sides": st.get("forbidden", {}),
    }


def segments_by_partner(edges, m, r):
    """Per partner the segments pin_plan gave it on the macro's sides:
    (side, lo, hi, bits), block-relative along the side in ORFS's
    direction (x for N and S, y for E and W, from the lower left)."""
    out = {}
    for (n, s), e in sorted(edges.items()):
        if n != m:
            continue
        for partner, bits, lo, hi in e["bundles"]:
            if s in "NS":
                a, b = lo - r[0], hi - r[0]
            else:
                a, b = (r[1] + r[3]) - hi, (r[1] + r[3]) - lo
            out.setdefault(partner, []).append((s, a, b, bits))
    return out


def place_buses(segs, buses):
    """Whole buses into a partner's segments, widest first into the segment
    with the most bits left: a bus keeps one side. [(side, lo, hi, buses)]."""
    left = [bits for _, _, _, bits in segs]
    given = [[] for _ in segs]
    for c in buses:
        i = max(range(len(segs)), key=lambda k: (left[k], -k))
        given[i].append(c)
        left[i] -= c["bits"]
    return [(s, a, b, g) for (s, a, b, _), g in zip(segs, given) if g]


def snap(rect, lattice):
    """A macro's origin down and outline up to the pin layers' lattice
    (constraints `lattice_um`, asap7's M2-M5 0.144 x 2.16 um), so its pins
    sit on the parent's tracks."""
    if not lattice:
        return rect
    lx, ly = lattice
    x = math.floor(rect[0] / lx + 1e-9) * lx
    y = math.floor(rect[1] / ly + 1e-9) * ly
    w = math.ceil(rect[2] / lx - 1e-9) * lx
    h = math.ceil(rect[3] / ly - 1e-9) * ly
    return [round(x, 3), round(y, 3), round(w, 3), round(h, 3)]


def side_pins(model, m, edges, r, up):
    """Per side of a macro, each whole bus's range: buses in the order of
    their partners' segments, each as long as its bits need at the layers
    the side's whole demand needs, from where its segment starts, pushed
    along when the one before it runs on and pulled back from the side's
    end. Block-relative, ORFS's direction."""
    per_side = {}
    for partner, segs in segments_by_partner(edges, m, r).items():
        for s, a, b, buses in place_buses(segs, bus_contributors(model, m, partner)):
            for c in buses:
                per_side.setdefault(s, []).append((a, c["bus"], c["bits"], partner))
    pins = {}
    for s, items in sorted(per_side.items()):
        length = up[2] if s in "NS" else up[3]
        ppu1 = model.ppu(s)
        total = sum(bits for _, _, bits, _ in items)
        layers = (
            min(model.c["pin_layers"], max(1, math.ceil(total / (length * ppu1))))
            if length
            else 1
        )
        ppu = ppu1 * layers
        rows = []
        cur = 0.0
        for start, bus, bits, partner in sorted(items):
            lo = max(cur, min(start, length))
            rows.append([lo, lo + bits / ppu, bus, bits, partner])
            cur = rows[-1][1]
        over = cur - length
        for i in range(len(rows) - 1, -1, -1):
            if over <= 0:
                break
            room = rows[i][0] - (rows[i - 1][1] if i else 0.0)
            shift = min(over, room)
            for row in rows[i:]:
                row[0] -= shift
                row[1] -= shift
            over -= shift
        pins[s] = [
            {
                "bus": bus,
                "partner": partner,
                "bits": bits,
                "range": [round(max(0.0, lo), 3), round(min(hi, length), 3)],
                "layer": model.pin_layer(s),
            }
            for lo, hi, bus, bits, partner in rows
        ]
    return pins


def floorplan(model, st):
    """floorplan.json: the die, each macro's place, outline and pins per
    bus, the glue's top pins."""
    die = st["die"]
    margin = model.c.get("core_margin_um", 2.0)
    out = {
        "die": [round(die[0], 3), round(die[1], 3)],
        "core": [margin, margin, round(die[0] - margin, 3), round(die[1] - margin, 3)],
        "macros": {},
        "report": {"pins_per_um": {}},
    }
    edges = st["edges"]
    for m in sorted(model.macros):
        r = st["rects"][m]
        up = snap(to_up(r, die[1]), model.c.get("lattice_um"))
        pins = side_pins(model, m, edges, r, up)
        out["macros"][m] = {
            "block": model.macros[m]["block"],
            "place": [up[0], up[1]],
            "shape": [up[2], up[3]],
            "orient": "R0",
            "pins": pins,
        }
        out["report"]["pins_per_um"][m] = {
            s: round(e["need"] / e["len"], 3)
            for (n, s), e in edges.items()
            if n == m and e["len"]
        }
    if st["internal"]:
        out["internal_placement"] = st["internal"]
    return out


def identity(paths, objs):
    out = {"tool": TOOL}
    for k, v in objs.items():
        out[k] = sha(v)
    return out


def write_md(v, path):
    lines = ["# Floorplan verdict: %s" % v["verdict"], ""]
    if v["stopped_at"]:
        lines.append("Stopped at rung `%s`." % v["stopped_at"])
        lines.append("")
    if v.get("die"):
        lines.append("Die: %.1f x %.1f um." % tuple(v["die"]))
        lines.append("")
    for f in v["findings"]:
        head = "## %s: %s, %s" % (f["rung"], f["status"], f.get("block"))
        if f.get("side"):
            head += " side %s" % f["side"]
        if f.get("kind"):
            head += " (%s)" % f["kind"]
        lines.append(head)
        lines.append("")
        for k in (
            "demand",
            "limit",
            "excess",
            "need",
            "slot",
            "free_fraction",
            "free_um",
            "pins_per_um_on_free",
            "aspect",
            "reason",
            "excess_um2",
        ):
            if k in f:
                lines.append("- %s: %s" % (k, json.dumps(f[k])))
        if f.get("walls"):
            lines.append("- walls: " + ", ".join(w["inst"] for w in f["walls"]))
        rows = f.get("contributors") or f.get("buses_needing")
        if rows:
            lines.append("")
            lines.append("| bus | bits | partner | registered |")
            lines.append("|---|---|---|---|")
            for c in rows:
                lines.append(
                    "| %s | %d | %s | %s |"
                    % (
                        c["bus"],
                        c["bits"],
                        c.get("partner", ""),
                        c.get("registered", ""),
                    )
                )
        if f.get("remedies"):
            lines.append("")
            lines.append("Remedies: " + ", ".join(f["remedies"]))
        lines.append("")
    if v.get("remedies"):
        lines += [
            "## Remedies, each run as a what-if",
            "",
            "| remedy | edit | effect |",
            "|---|---|---|",
        ]
        for r in v["remedies"]:
            edit = {k: x for k, x in r.items() if k not in ("kind", "effect", "for")}
            e = r.get("effect")
            if isinstance(e, dict):
                eff = e["verdict"] + (
                    " at %s %s" % (e["stopped_at"], json.dumps(e.get("first", {})))
                    if e["stopped_at"]
                    else ""
                )
            else:
                eff = e or "not modelled"
            lines.append("| %s | %s | %s |" % (r["kind"], json.dumps(edit), eff))
        lines.append("")
    if v.get("chains"):
        lines += [
            "## Worst chains across boundaries",
            "",
            "| chain | logic ps | wire budget ps | layer | length um | slack ps |",
            "|---|---|---|---|---|---|",
        ]
        for c in v["chains"]:
            route = c.get("route", {})
            lines.append(
                "| %s | %.0f | %.0f | %s | %s | %.0f |"
                % (
                    c["chain"],
                    sum(l["ps"] for l in c["legs"]),
                    c["wire_budget_ps"],
                    c.get("layer_needed"),
                    route.get("length_um", ""),
                    c["slack_ps"],
                )
            )
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def run(blocks, parent, pdk, cut, constraints, run_all=False, remedies=True):
    """(model, state, verdict, floorplan or None). With `remedies`, every
    remedy of the failed findings with its effect (remedies.py)."""
    model = Model(blocks, parent, pdk, cut, constraints)
    st = plan(model)
    ident = identity(
        None,
        {
            "blocks": sorted((b["block"], b.get("identity", {})) for b in blocks),
            "parent": parent or {},
            "pdk": pdk.get("identity", pdk),
            "cut": cut,
            "constraints": constraints,
        },
    )
    v = verdict(model, st, ident, run_all)
    v["chains"] = st.get("chains", [])[:10]
    if remedies and v["verdict"] != "feasible":
        import remedies as R

        fails = [f for f in v["findings"] if f["status"] == "fail"]
        if not run_all:
            fails = [f for f in fails if f["rung"] == v["stopped_at"]][:2]
        inputs = {
            "blocks": blocks,
            "parent": parent,
            "pdk": pdk,
            "cut": cut,
            "constraints": constraints,
        }
        v["remedies"] = R.compute(
            lambda i: run(remedies=False, **i)[2], inputs, model, st, fails
        )
    fp = floorplan(model, st) if v["verdict"] == "feasible" else None
    return model, st, v, fp


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--block", action="append", default=[], help="a block.json, once per macro"
    )
    ap.add_argument("--parent", help="parent.json")
    ap.add_argument("--pdk", required=True)
    ap.add_argument("--cut", required=True)
    ap.add_argument("--constraints", required=True)
    ap.add_argument("--verdict", required=True, help="verdict.json to write")
    ap.add_argument("--verdict-md", help="verdict.md to write")
    ap.add_argument("--floorplan", help="floorplan.json to write; {} when infeasible")
    ap.add_argument("--all", action="store_true", help="every rung past the first stop")
    ap.add_argument(
        "--no-remedies", action="store_true", help="name no remedies, run no what-ifs"
    )
    args = ap.parse_args(argv)
    blocks = [read_json(p) for p in args.block]
    parent = read_json(args.parent) if args.parent else None
    model, st, v, fp = run(
        blocks,
        parent,
        read_json(args.pdk),
        read_json(args.cut),
        read_json(args.constraints),
        args.all,
        not args.no_remedies,
    )
    with open(args.verdict, "w") as f:
        json.dump(v, f, indent=1, sort_keys=True)
        f.write("\n")
    if args.verdict_md:
        write_md(v, args.verdict_md)
    if args.floorplan:
        with open(args.floorplan, "w") as f:
            json.dump(fp or {}, f, indent=1, sort_keys=True)
            f.write("\n")
    print(
        "plan: %s%s"
        % (v["verdict"], " at " + v["stopped_at"] if v["stopped_at"] else "")
    )
    for f in v["findings"]:
        if f["status"] == "fail":
            print(
                "  %s %s %s %s %s"
                % (
                    f["rung"],
                    f.get("kind", ""),
                    f.get("block"),
                    f.get("side", ""),
                    f.get("bus", ""),
                )
            )
    for r in v.get("remedies", []):
        print("  remedy %s %s" % (r["kind"], json.dumps(r.get("effect"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
